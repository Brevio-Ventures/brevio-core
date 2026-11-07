"""``brevio-core init`` and ``init --undo``, run in a clean interpreter with only a release tree on its path.

Standard library only: the exporter copies this file beside the code (the 0.4 set) and it runs unchanged there. The
test runs on a private copy of the tree, given a ``VERSION`` and a ``pyproject.toml`` the way a release has them, so
the pinned version and the repository it names are known. Every command runs on a temporary git repository, with a
PATH that finds git and nothing else and stdin that is not a terminal.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EXPORTER = os.path.join(ROOT, "tools", "export_core.py")      # present in the harness checkout only
VERSION = "0.4.7"
REPO_URL = "https://brevio.pro/acme/brevio-core"              # the release's Source URL; a public address
_RUN = "import sys; sys.path.insert(0, sys.argv[1]); from brevio.pipeline import core_cli; raise SystemExit(core_cli.main(sys.argv[2:]))"
_SKILL = "skills/brevio-core/SKILL.md"
_TMP = tempfile.TemporaryDirectory()
TREE = os.path.join(_TMP.name, "core")
BIN = os.path.join(_TMP.name, "bin")
PRECOMMIT = "repos:\n- repo: local\n  hooks:\n  - id: mine\n    entry: true\n    language: system\ndefault_stages: [pre-commit]\n"
MCP = '{\n  "mcpServers": {\n    "other": {"command": "other-server"}\n  }\n}\n'


def setUpModule():
    if os.path.isfile(EXPORTER):
        subprocess.run([sys.executable, EXPORTER, "--out", TREE, "--set", "0.4"], check=True, capture_output=True, timeout=120)
    else:
        shutil.copytree(ROOT, TREE, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    with open(os.path.join(TREE, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(VERSION + "\n")
    with open(os.path.join(TREE, "pyproject.toml"), "w", encoding="utf-8") as fh:
        fh.write(f'[project]\nname = "brevio-core"\n\n[project.urls]\nSource = "{REPO_URL}"\n')
    os.makedirs(BIN)
    os.symlink(shutil.which("git"), os.path.join(BIN, "git"))


def tearDownModule():
    _TMP.cleanup()


def run_cli(cwd, *args, stdin=None, env=None):
    e = {"PATH": BIN, "HOME": cwd} if env is None else env
    kwargs = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run([sys.executable, "-I", "-c", _RUN, TREE, *args], cwd=cwd, capture_output=True, text=True,
                          timeout=120, env=e, **kwargs)


def write(d, rel, text):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8", newline="") as fh:
        return fh.read()


def snapshot(d):
    """Every file and folder under ``d`` (the git folder only for its exclude file), with a hash of each file."""
    out = {}
    for dirpath, dirs, names in os.walk(d):
        rel_dir = os.path.relpath(dirpath, d)
        if rel_dir.split(os.sep)[0] == ".git":
            continue
        dirs[:] = [x for x in dirs if x != ".git"]
        out[rel_dir + "/"] = ""
        for n in names:
            with open(os.path.join(dirpath, n), "rb") as fh:
                out[os.path.join(rel_dir, n)] = hashlib.sha256(fh.read()).hexdigest()
    out[".git/info/exclude"] = read(d, ".git/info/exclude") if os.path.exists(os.path.join(d, ".git/info/exclude")) else None
    return out


def repo(**files):
    """A temporary git repository holding ``files`` (``rel=text``; ``__`` in a name stands for ``/``)."""
    d = tempfile.TemporaryDirectory()
    subprocess.run(["git", "init", "-q", "-b", "main", d.name], check=True, capture_output=True)
    for rel, text in files.items():
        write(d.name, rel.replace("__", "/"), text)
    return d


class TestInitOnAnEmptyRepository(unittest.TestCase):
    def test_init_writes_the_pinned_workflow_and_the_agent_rules_and_records_each_with_a_hash(self):
        with repo() as d:
            res = run_cli(d, "init", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            flow = read(d, ".github/workflows/brevio-core.yml")
            self.assertIn(f"uses: acme/brevio-core@v{VERSION}\n", flow)
            self.assertIn(f"package-version: {VERSION}\n", flow)
            self.assertNotIn("@v0\n", flow)
            others = [u for u in re.findall(r"uses: (\S+)", flow) if not u.startswith("acme/")]
            self.assertTrue(others and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in others), others)
            self.assertNotIn("pull_request_target", flow)
            self.assertIn("on:\n  pull_request:\n  merge_group:\n", flow)
            top, job = flow.split("jobs:")
            self.assertIn("permissions:\n  contents: read\n", top)
            self.assertNotIn("pull-requests", top)
            self.assertIn("pull-requests: write", job)
            self.assertIn("brevio-core:start", read(d, "AGENTS.md"))
            record = json.loads(read(d, ".brevio/init.json"))
            for entry in record["entries"]:
                self.assertEqual(entry["sha256"], hashlib.sha256(read(d, entry["path"]).encode()).hexdigest())
            self.assertLessEqual({".github/workflows/brevio-core.yml", "AGENTS.md"}, {e["path"] for e in record["entries"]})
            for written in (".github/workflows/brevio-core.yml", "AGENTS.md"):
                self.assertIn(f"wrote {written}", res.stdout)
            self.assertIn(f"[![checked by brevio-core](https://img.shields.io/badge/checked%20by-brevio--core-blue)]({REPO_URL})",
                          res.stdout)

    def test_the_default_writes_no_pre_commit_hook_or_mcp_config(self):
        with repo(CLAUDE__md="# notes\n") as d:
            os.makedirs(os.path.join(d, ".cursor"))
            self.assertEqual(run_cli(d, "init", "--yes").returncode, 0)
            for rel in (".pre-commit-config.yaml", ".mcp.json", ".cursor/mcp.json", ".cursor/rules/brevio-core.mdc"):
                self.assertFalse(os.path.exists(os.path.join(d, rel)), rel)

    def test_init_twice_writes_nothing_new(self):
        with repo(CLAUDE__md="# notes\n", package__json="{}\n") as d:
            os.makedirs(os.path.join(d, ".cursor"))
            self.assertEqual(run_cli(d, "init", "--with", "precommit,hook,mcp", "--yes").returncode, 0)
            before = snapshot(d)
            again = run_cli(d, "init", "--with", "precommit,hook,mcp", "--yes")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("nothing to write", again.stdout)
            self.assertEqual(snapshot(d), before)

    def test_outside_a_git_repository_init_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            res = run_cli(d, "init", "--yes")
            self.assertEqual(res.returncode, 2)
            self.assertIn("not inside a git repository", res.stderr)

    def test_an_unknown_part_is_a_usage_error(self):
        with repo() as d:
            self.assertEqual(run_cli(d, "init", "--with", "everything", "--yes").returncode, 2)


class TestDryRun(unittest.TestCase):
    def test_dry_run_and_no_terminal_without_yes_both_write_nothing_and_show_the_plan(self):
        for args in (("--dry-run", "--yes"), ()):
            with repo(**{".pre-commit-config.yaml": PRECOMMIT}) as d:
                before = snapshot(d)
                res = run_cli(d, "init", "--with", "precommit,hook,mcp", *args)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(snapshot(d), before, args)
                self.assertIn("create .github/workflows/brevio-core.yml", res.stdout)
                self.assertIn(f"+- repo: {REPO_URL}", res.stdout)
                self.assertIn("nothing was written" if not args else "dry run", res.stdout)


class TestExistingFilesArePreserved(unittest.TestCase):
    def test_the_pre_commit_config_and_the_mcp_config_keep_every_existing_entry_byte_for_byte(self):
        with repo(**{".pre-commit-config.yaml": PRECOMMIT, ".mcp.json": MCP, "CLAUDE.md": "# notes\n"}) as d:
            res = run_cli(d, "init", "--with", "precommit,mcp", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            pre = read(d, ".pre-commit-config.yaml")
            self.assertTrue(pre.endswith("default_stages: [pre-commit]\n"))
            self.assertIn(f"- repo: {REPO_URL}\n  rev: v{VERSION}\n  hooks:\n    - id: brevio-core\n", pre)
            self.assertEqual(pre.replace(f"- repo: {REPO_URL}\n  rev: v{VERSION}\n  hooks:\n    - id: brevio-core\n", ""), PRECOMMIT)
            servers = json.loads(read(d, ".mcp.json"))["mcpServers"]
            self.assertEqual(servers["other"], {"command": "other-server"})
            self.assertEqual(servers["brevio-core"], {"command": "uvx", "args": [f"brevio-core=={VERSION}", "mcp"]})
            self.assertIn('"other": {"command": "other-server"}', read(d, ".mcp.json"))
            self.assertIn("/.mcp.json\n", read(d, ".git/info/exclude"))
            self.assertIn("@AGENTS.md\n", read(d, "CLAUDE.md"))
            self.assertTrue(read(d, "CLAUDE.md").startswith("# notes\n"))

    def test_a_tracked_mcp_config_is_left_alone(self):
        with repo(**{".mcp.json": MCP, "CLAUDE.md": "# notes\n"}) as d:
            subprocess.run(["git", "-C", d, "add", ".mcp.json"], check=True, capture_output=True)
            res = run_cli(d, "init", "--with", "mcp", "--yes")
            self.assertEqual(read(d, ".mcp.json"), MCP)
            self.assertIn("tracked by git", res.stdout)

    def test_the_hook_is_pinned_personal_and_written_by_hook_install(self):
        with repo() as d:
            os.makedirs(os.path.join(d, ".claude"))
            res = run_cli(d, "init", "--with", "hook", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            hooks = json.loads(read(d, ".claude/settings.json"))["hooks"]
            self.assertEqual({event: [h["command"] for g in groups for h in g["hooks"]] for event, groups in hooks.items()},
                             {"PostToolUse": [f"uvx brevio-core=={VERSION} hook run --event post-edit",
                                              f"uvx brevio-core=={VERSION} hook run --event post-command"],
                              "Stop": [f"uvx brevio-core=={VERSION} hook run --event stop"]})
            self.assertIn("/.claude/settings.json\n", read(d, ".git/info/exclude"))
            self.assertIn("git-ignored", res.stdout)
            self.assertEqual(subprocess.run(["git", "-C", d, "status", "--porcelain", "--", ".claude"],
                                            capture_output=True, text=True).stdout, "")

    def test_cursor_gets_its_pinned_hooks_file_and_undo_removes_it(self):
        with repo() as d:
            os.makedirs(os.path.join(d, ".cursor"))
            self.assertEqual(run_cli(d, "init", "--with", "hook", "--without", "action,agents-md,baseline", "--yes").returncode, 0)
            hooks = json.loads(read(d, ".cursor/hooks.json"))["hooks"]
            self.assertEqual({event: [h["command"] for h in entries] for event, entries in hooks.items()},
                             {"postToolUse": [f"uvx brevio-core=={VERSION} hook run --event post-edit --client cursor",
                                              f"uvx brevio-core=={VERSION} hook run --event post-command --client cursor"],
                              "stop": [f"uvx brevio-core=={VERSION} hook run --event stop --client cursor"]})
            self.assertIn("/.cursor/hooks.json\n", read(d, ".git/info/exclude"))
            self.assertEqual(run_cli(d, "init", "--undo", "--yes").returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(d, ".cursor", "hooks.json")))


class TestTheAgentRules(unittest.TestCase):
    def test_the_agents_md_block_and_the_cursor_rule_carry_the_rules_of_the_shipped_skill(self):
        with repo(**{"AGENTS.md": "# Team rules\n\nBe kind.\n"}) as d:
            os.makedirs(os.path.join(d, ".cursor"))
            self.assertEqual(run_cli(d, "init", "--yes").returncode, 0)
            text = read(d, "AGENTS.md")
            self.assertTrue(text.startswith("# Team rules\n\nBe kind.\n"))
            block = re.search(r"<!-- brevio-core:start -->\n## brevio-core\n\n(.*?)<!-- brevio-core:end -->\n", text, re.S)
            self.assertIsNotNone(block)
            rules = block.group(1)
            self.assertLessEqual(len(rules.splitlines()), 5)
            self.assertIn(rules, read(TREE, _SKILL))
            self.assertIn(rules, read(d, ".cursor/rules/brevio-core-agents.mdc"))
            self.assertIn("brevio-core learn", rules)

    def test_without_agents_md_leaves_agents_md_out(self):
        with repo() as d:
            self.assertEqual(run_cli(d, "init", "--without", "agents-md", "--yes").returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(d, "AGENTS.md")))


class TestInstalledMetadata(unittest.TestCase):
    """The installed version is read from METADATA by hand: importlib.metadata would load socket on 3.11 and 3.12."""

    _PROBE = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]); "
              "from brevio.pipeline import core_init; m = core_init.installed_metadata('brevio-core'); "
              "print(m and (m['Version'], m['Project-URL'])); "
              "print(sorted(x for x in ('socket', 'email', 'ssl') if x in sys.modules))")

    def test_the_version_and_source_come_from_the_dist_info_without_loading_a_network_module(self):
        with tempfile.TemporaryDirectory() as site:
            dist = os.path.join(site, "brevio_core-1.2.3.dist-info")
            os.makedirs(dist)
            with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as fh:
                fh.write("Metadata-Version: 2.4\nName: brevio-core\nVersion: 1.2.3\n"
                         "Project-URL: Source, https://brevio.pro/brevio-core\n\nVersion: 9.9.9 in the body\n")
            out = subprocess.run([sys.executable, "-I", "-c", self._PROBE, TREE, site], capture_output=True, text=True,
                                 timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            lines = out.stdout.strip().splitlines()
            self.assertEqual(lines[0], "(['1.2.3'], ['Source, https://brevio.pro/brevio-core'])")
            self.assertEqual(lines[1], "[]")


class TestUndo(unittest.TestCase):
    def test_undo_restores_the_original_tree_byte_for_byte(self):
        files = {".pre-commit-config.yaml": PRECOMMIT, ".mcp.json": MCP, "CLAUDE.md": "# notes", "AGENTS.md": "rules\n",
                 ".claude/settings.json": '{"permissions": {"allow": []}}', "package.json": "{}\n"}
        with repo(**files) as d:
            os.makedirs(os.path.join(d, ".cursor"))
            before = snapshot(d)
            self.assertEqual(run_cli(d, "init", "--with", "precommit,hook,mcp", "--yes").returncode, 0)
            self.assertNotEqual(snapshot(d), before)
            res = run_cli(d, "init", "--undo", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(snapshot(d), before)

    def test_undo_without_yes_and_without_a_terminal_removes_nothing(self):
        with repo() as d:
            run_cli(d, "init", "--yes")
            after = snapshot(d)
            self.assertEqual(run_cli(d, "init", "--undo").returncode, 0)
            self.assertEqual(snapshot(d), after)

    def test_undo_after_a_user_edit_leaves_the_edited_file_and_lists_it(self):
        with repo(**{".pre-commit-config.yaml": PRECOMMIT}) as d:
            self.assertEqual(run_cli(d, "init", "--with", "precommit", "--yes").returncode, 0)
            with open(os.path.join(d, ".github/workflows/brevio-core.yml"), "a", encoding="utf-8") as fh:
                fh.write("# my change\n")
            with open(os.path.join(d, ".pre-commit-config.yaml"), "a", encoding="utf-8") as fh:
                fh.write("# mine too\n")
            res = run_cli(d, "init", "--undo", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(read(d, ".github/workflows/brevio-core.yml").endswith("# my change\n"))
            self.assertIn("left .github/workflows/brevio-core.yml", res.stdout)
            self.assertEqual(read(d, ".pre-commit-config.yaml"), PRECOMMIT + "# mine too\n")   # only its entry went
            self.assertFalse(os.path.exists(os.path.join(d, "AGENTS.md")))
            record = json.loads(read(d, ".brevio/init.json"))
            self.assertEqual([e["path"] for e in record["entries"]], [".github/workflows/brevio-core.yml"])


class TestStackDetection(unittest.TestCase):
    def test_empty_repository_has_empty_stack(self):
        with repo() as d:
            res = subprocess.run([sys.executable, "-I", "-c",
                                  f"import sys; sys.path.insert(0, {TREE!r}); from brevio.pipeline import core_init; print(core_init.detect_stack({d!r}))"],
                                 capture_output=True, text=True, check=True)
            self.assertEqual(res.stdout.strip(), "[]")

    def test_detects_all_stack_markers(self):
        with repo(**{"pyproject.toml": "[project]\n", "package.json": "{}\n", "tsconfig.json": "{}\n",
                     "Dockerfile": "FROM scratch\n", "prisma__schema.prisma": "datasource db {}\n"}) as d:
            res = subprocess.run([sys.executable, "-I", "-c",
                                  f"import sys; sys.path.insert(0, {TREE!r}); from brevio.pipeline import core_init; print(core_init.detect_stack({d!r}))"],
                                 capture_output=True, text=True, check=True)
            self.assertEqual(res.stdout.strip(), "['Python', 'Node/TS', 'TypeScript', 'Docker', 'Database/Migrations']")


class TestLiveHookSelftest(unittest.TestCase):
    def test_live_hook_selftest_returns_expected_receipt_with_zero_disk_writes(self):
        cmd = f"import sys; sys.path.insert(0, {TREE!r}); from brevio.pipeline import core_init; print(core_init.live_hook_selftest())"
        res = subprocess.run([sys.executable, "-I", "-c", cmd], capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout.strip(), "verified in-memory gate: caught [R9.1] untyped escape hatch (0 files touched)")


class TestAgentDetectionWithCli(unittest.TestCase):
    def test_cli_on_path_triggers_agent_detection(self):
        with repo() as d:
            bin_dir = os.path.join(d, "mock_bin")
            os.makedirs(bin_dir)
            for cli_name in ("cursor", "claude", "hermes"):
                path = os.path.join(bin_dir, cli_name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("#!/bin/sh\nexit 0\n")
                os.chmod(path, 0o755)
            custom_env = {"PATH": f"{bin_dir}:{BIN}", "HOME": d}
            cmd = (f"import sys; sys.path.insert(0, {TREE!r}); from brevio.pipeline import core_init; "
                   f"import json; print(json.dumps(core_init.detect_agents({d!r})))")
            res = subprocess.run([sys.executable, "-I", "-c", cmd], capture_output=True, text=True, env=custom_env, check=True)
            agents = json.loads(res.stdout.strip())
            self.assertTrue(agents.get("cursor"))
            self.assertTrue(agents.get("claude_code"))
            self.assertTrue(agents.get("hermes"))


class TestPersonalMode(unittest.TestCase):
    def test_personal_mode_stealth_touches_zero_tracked_files(self):
        with repo() as d:
            os.makedirs(os.path.join(d, ".cursor"))
            before = snapshot(d)
            res = run_cli(d, "init", "--personal", "--yes")
            self.assertEqual(res.returncode, 0, res.stderr)
            # git status must show zero untracked or modified files
            st = subprocess.run(["git", "-C", d, "status", "--porcelain"], capture_output=True, text=True, check=True)
            self.assertEqual(st.stdout.strip(), "")
            # Exclude file must contain .brevio/ and .agents/
            exclude_text = read(d, ".git/info/exclude")
            self.assertIn("/.brevio/\n", exclude_text)
            self.assertIn("/.agents/\n", exclude_text)
            self.assertIn("/.cursor/hooks.json\n", exclude_text)
            self.assertIn("/.cursor/mcp.json\n", exclude_text)
            # Workflow and AGENTS.md must NOT exist
            self.assertFalse(os.path.exists(os.path.join(d, ".github/workflows/brevio-core.yml")))
            self.assertFalse(os.path.exists(os.path.join(d, "AGENTS.md")))
            # Undo must cleanly restore snapshot byte-for-byte
            res_undo = run_cli(d, "init", "--undo", "--yes")
            self.assertEqual(res_undo.returncode, 0, res_undo.stderr)
            self.assertEqual(snapshot(d), before)


class TestInteractiveWizard(unittest.TestCase):
    def test_wizard_profile_1_full_protection(self):
        with repo(**{"pyproject.toml": "[project]\n"}) as d:
            os.makedirs(os.path.join(d, ".cursor"))
            res = run_cli(d, "init", "--wizard", stdin="1\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("stack detected: Python", res.stdout)
            self.assertIn("coding agents found: Cursor", res.stdout)
            self.assertIn("verified in-memory gate: caught [R9.1] untyped escape hatch (0 files touched)", res.stdout)
            # Full protection writes workflow, AGENTS.md, baseline, hook, and mcp
            self.assertTrue(os.path.exists(os.path.join(d, ".github/workflows/brevio-core.yml")))
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(d, ".brevio/baseline.json")))
            self.assertTrue(os.path.exists(os.path.join(d, ".cursor/hooks.json")))

    def test_wizard_profile_2_stealth_mode(self):
        with repo(**{"package.json": "{}\n"}) as d:
            os.makedirs(os.path.join(d, ".cursor"))
            res = run_cli(d, "init", "--wizard", stdin="2\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("stack detected: Node/TS", res.stdout)
            self.assertIn("verified in-memory gate: caught [R9.1] untyped escape hatch (0 files touched)", res.stdout)
            # Stealth mode writes hook and mcp only, no workflow, no AGENTS.md, no baseline
            self.assertFalse(os.path.exists(os.path.join(d, ".github/workflows/brevio-core.yml")))
            self.assertFalse(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertFalse(os.path.exists(os.path.join(d, ".brevio/baseline.json")))
            self.assertTrue(os.path.exists(os.path.join(d, ".cursor/hooks.json")))
            # Exclude contains .brevio/ and .agents/
            exclude_text = read(d, ".git/info/exclude")
            self.assertIn("/.brevio/\n", exclude_text)
            self.assertIn("/.agents/\n", exclude_text)

    def test_wizard_profile_3_ci_gate_only(self):
        with repo() as d:
            os.makedirs(os.path.join(d, ".cursor"))
            res = run_cli(d, "init", "--wizard", stdin="3\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("stack detected: generic", res.stdout)
            self.assertIn("verified in-memory gate: caught [R9.1] untyped escape hatch (0 files touched)", res.stdout)
            # CI gate only writes workflow, AGENTS.md, baseline, NO hooks or mcp
            self.assertTrue(os.path.exists(os.path.join(d, ".github/workflows/brevio-core.yml")))
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(d, ".brevio/baseline.json")))
            self.assertFalse(os.path.exists(os.path.join(d, ".cursor/hooks.json")))
            self.assertFalse(os.path.exists(os.path.join(d, ".cursor/mcp.json")))

    def test_wizard_default_enter_selects_profile_1(self):
        with repo() as d:
            res = run_cli(d, "init", "--wizard", stdin="\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, ".github/workflows/brevio-core.yml")))
            self.assertTrue(os.path.exists(os.path.join(d, "AGENTS.md")))
            self.assertIn("verified in-memory gate: caught [R9.1] untyped escape hatch (0 files touched)", res.stdout)

    def test_wizard_warmstarts_trial_guards_from_recent_fix_commits(self):
        with repo(**{"src/calc.py": "result = compute_legacy_total(items)\n"}) as d:
            g = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run([*g, "add", "."], check=True, capture_output=True)
            subprocess.run([*g, "commit", "-q", "-m", "initial"], check=True, capture_output=True)
            write(d, "src/calc.py", "result = compute_total(items)\n")
            subprocess.run([*g, "commit", "-q", "-am", "fix: replace legacy total calculation"], check=True, capture_output=True)
            res = run_cli(d, "init", "--wizard", stdin="1\n")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("warm-start: seeded 1 trial guard(s) from recent fix commits", res.stdout)
            guards_path = os.path.join(d, ".brevio", "guards.json")
            self.assertTrue(os.path.isfile(guards_path))
            guards = json.loads(read(d, ".brevio/guards.json")).get("guards", {})
            self.assertEqual(len(guards), 1)
            self.assertEqual(next(iter(guards.values()))["status"], "trial")
            # Undo removes warm-started guards.json and .agents/rules/*.md cleanly
            res_undo = run_cli(d, "init", "--undo", "--yes")
            self.assertEqual(res_undo.returncode, 0, res_undo.stderr)
            self.assertFalse(os.path.exists(guards_path))
            self.assertFalse(os.path.exists(os.path.join(d, ".agents")))


if __name__ == "__main__":
    unittest.main()
