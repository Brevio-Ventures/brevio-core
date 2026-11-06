"""The ``brevio-core scan`` command, run in a clean interpreter with only the exported tree on its path.

Standard library only: the exporter copies this file beside the code and it runs unchanged in the exported tree.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from brevio.pipeline.code_rules import PR_RULES_122

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
# A fake key in the AWS access key format (AWS's documented example key ID), joined at run time so this file is not
# itself a finding of a secret scan. The hardcoded-secret rule (R13.1) flags the format (E35 precision run, 2026-11-05).
AWS_EXAMPLE_LINE = "const apiKey = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "';\n"
CLEAN_LINE = "export const add = (a: number, b: number): number => a + b;\n"
_RUN = "import sys; sys.path.insert(0, sys.argv[1]); from brevio.pipeline import core_cli; raise SystemExit(core_cli.main(sys.argv[2:]))"


def run_cli(cwd, *args):
    """``brevio-core`` with ``args`` in ``cwd``, under ``python -I`` so nothing but the standard library and ROOT loads."""
    return subprocess.run([sys.executable, "-I", "-c", _RUN, ROOT, *args], cwd=cwd, capture_output=True, text=True, timeout=60)


def write(d, rel, text):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def git(d, *args):
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True, capture_output=True)


class TestScanCommand(unittest.TestCase):
    def test_a_planted_secret_fails_the_scan_and_a_clean_file_passes(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "src/bad.ts", AWS_EXAMPLE_LINE)
            write(d, "src/ok.ts", CLEAN_LINE)
            bad = run_cli(d, "scan", "src/bad.ts")
            self.assertEqual(bad.returncode, 1, bad.stderr)
            self.assertIn("src/bad.ts:1: [R13.1]", bad.stdout)
            self.assertEqual(run_cli(d, "scan", "src/ok.ts").returncode, 0)

    def test_a_diff_scan_skips_build_output(self):
        """CI installs the package, which writes build/lib copies; those are not the change (2026-11-05)."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "app.ts", CLEAN_LINE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")
            write(d, "build/lib/pkg/x.py", AWS_EXAMPLE_LINE)
            write(d, "pkg.egg-info/x.py", AWS_EXAMPLE_LINE)
            r = run_cli(d, "scan", "--diff", "HEAD")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            write(d, "src/y.ts", AWS_EXAMPLE_LINE)
            self.assertEqual(run_cli(d, "scan", "--diff", "HEAD").returncode, 1)

    # Third-party code kept in a repository gave most false positives of the E35 precision run: Playwright keeps
    # minified and bundled builds as test assets (docs/benchmarks/precision.md, 2026-11-05).
    UPSTREAM = {"third_party/lib/a.ts": AWS_EXAMPLE_LINE, "third-party/b.js": "eval(code);\n", "src/vendor/c.ts": AWS_EXAMPLE_LINE,
                "assets/modernizr.min.js": "eval(code);\n", "assets/lib.min.mjs": "eval(code);\n",
                "static/js/main.3f2a1b9c.chunk.js": "eval(code);\n", "dist2/app.bundle.js": "eval(code);\n",
                "out/index-4be0c13d.js": "eval(code);\n",
                "tests/assets/modernizr/modernizr.js": "(()=>{var j=0;" + "x=1;" * 200 + "})();\n" + "eval(code);\n"}

    def test_a_folder_scan_skips_vendored_minified_and_bundled_files(self):
        with tempfile.TemporaryDirectory() as d:
            for rel, text in self.UPSTREAM.items():
                write(d, rel, text)
            write(d, "src/own.ts", "const header = 'x';\n" + AWS_EXAMPLE_LINE)
            write(d, "src/index-page.js", "eval(code);\n")          # a word after the dash, not a hash
            res = run_cli(d, "scan")
            self.assertEqual(res.returncode, 1, res.stderr)
            self.assertEqual(sorted({ln.split(":")[0] for ln in res.stdout.splitlines() if ": [R" in ln}),
                             ["src/index-page.js", "src/own.ts"])

    def test_a_diff_scan_skips_vendored_minified_and_bundled_files(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "app.ts", CLEAN_LINE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")
            for rel, text in self.UPSTREAM.items():
                write(d, rel, text)
            git(d, "add", "-A")                                    # tracked, so the diff carries them, not ls-files
            r = run_cli(d, "scan", "--diff", "HEAD")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_scan_mode_skips_typescript_declaration_files(self):
        """A declaration holds no code that runs; Playwright's protocol.d.ts gave R2.8 hits on doc prose (E35, 2026-11-06)."""
        prose = "which includes eval(), Function(), setTimeout() and setInterval()\n"
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "app.ts", CLEAN_LINE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")
            for rel in ("types/protocol.d.ts", "types/index.d.mts", "types/index.d.cts"):
                write(d, rel, prose + AWS_EXAMPLE_LINE)
            for args in (("scan",), ("scan", "types"), ("scan", "--file", "types/protocol.d.ts"), ("scan", "--diff", "HEAD")):
                r = run_cli(d, *args)
                self.assertEqual((r.returncode, r.stdout), (0, ""), args)
            write(d, "types/protocol.ts", prose)
            self.assertIn("types/protocol.ts:1: [R2.8]", run_cli(d, "scan").stdout)

    def test_a_folder_is_walked_and_the_default_is_the_current_folder(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "src/deep/bad.ts", AWS_EXAMPLE_LINE)
            write(d, "node_modules/pkg/bad.ts", AWS_EXAMPLE_LINE)
            res = run_cli(d, "scan")
            self.assertEqual(res.returncode, 1)
            self.assertIn("src/deep/bad.ts", res.stdout)
            self.assertNotIn("node_modules", res.stdout)

    def test_the_agent_hook_form_scan_file_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.ts", AWS_EXAMPLE_LINE)
            write(d, "b.ts", CLEAN_LINE)
            self.assertEqual(run_cli(d, "scan", "--file", "a.ts").returncode, 1)
            self.assertEqual(run_cli(d, "scan", "--file", "b.ts").returncode, 0)

    def test_a_missing_path_is_a_usage_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d:
            res = run_cli(d, "scan", "--file", "nope.ts")
            self.assertEqual(res.returncode, 2)
            self.assertIn("no such file", res.stderr)

    def test_sarif_is_written_to_the_named_file_with_the_rule_and_line(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "src/bad.ts", CLEAN_LINE + AWS_EXAMPLE_LINE)
            res = run_cli(d, "scan", "src/bad.ts", "--sarif", "out.sarif")
            self.assertEqual(res.returncode, 1)
            with open(os.path.join(d, "out.sarif"), encoding="utf-8") as fh:
                log = json.load(fh)
            self.assertEqual(log["version"], "2.1.0")
            hit = log["runs"][0]["results"][0]
            self.assertEqual(hit["ruleId"], "R13.1")
            self.assertEqual(hit["locations"][0]["physicalLocation"]["region"]["startLine"], 2)
            self.assertEqual(len(log["runs"][0]["tool"]["driver"]["rules"]), len(PR_RULES_122))

    def test_diff_mode_flags_only_the_lines_added_against_the_base(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            write(d, "src/old.ts", AWS_EXAMPLE_LINE)    # already on main: not this change's problem
            git(d, "add", ".")
            git(d, "commit", "-q", "-m", "base")
            self.assertEqual(run_cli(d, "scan", "--diff", "main").returncode, 0)
            write(d, "src/new.ts", CLEAN_LINE + AWS_EXAMPLE_LINE)
            write(d, "src/old.ts", AWS_EXAMPLE_LINE + "eval('2 + 2');\n")
            res = run_cli(d, "scan", "--diff", "main")
            self.assertEqual(res.returncode, 1, res.stderr)
            self.assertIn("src/new.ts:2: [R13.1]", res.stdout)
            self.assertIn("src/old.ts:2:", res.stdout)
            self.assertNotIn("src/old.ts:1:", res.stdout)


class TestLeaksCommand(unittest.TestCase):
    def test_leaks_fails_on_a_stray_email_and_passes_a_clean_folder(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.md", "write to someone" + "@corp-mail.io\n")
            res = run_cli(d, "leaks")
            self.assertEqual(res.returncode, 1)
            self.assertIn("a.md: email:", res.stdout)
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.md", "write to you@example.com\n")
            self.assertEqual(run_cli(d, "leaks").returncode, 0)


if __name__ == "__main__":
    unittest.main()
