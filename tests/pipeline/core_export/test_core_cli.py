"""The ``brevio-core scan`` command, run in a clean interpreter with only the exported tree on its path.

Standard library only: the exporter copies this file beside the code and it runs unchanged in the exported tree.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SECRET_LINE = "const apiKey = 'fake_secret_key_1234567890abcdef';\n"
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
            write(d, "src/bad.ts", SECRET_LINE)
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
            write(d, "build/lib/pkg/x.py", SECRET_LINE)
            write(d, "pkg.egg-info/x.py", SECRET_LINE)
            r = run_cli(d, "scan", "--diff", "HEAD")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            write(d, "src/y.ts", SECRET_LINE)
            self.assertEqual(run_cli(d, "scan", "--diff", "HEAD").returncode, 1)

    def test_a_folder_is_walked_and_the_default_is_the_current_folder(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "src/deep/bad.ts", SECRET_LINE)
            write(d, "node_modules/pkg/bad.ts", SECRET_LINE)
            res = run_cli(d, "scan")
            self.assertEqual(res.returncode, 1)
            self.assertIn("src/deep/bad.ts", res.stdout)
            self.assertNotIn("node_modules", res.stdout)

    def test_the_agent_hook_form_scan_file_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "a.ts", SECRET_LINE)
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
            write(d, "src/bad.ts", CLEAN_LINE + SECRET_LINE)
            res = run_cli(d, "scan", "src/bad.ts", "--sarif", "out.sarif")
            self.assertEqual(res.returncode, 1)
            with open(os.path.join(d, "out.sarif"), encoding="utf-8") as fh:
                log = json.load(fh)
            self.assertEqual(log["version"], "2.1.0")
            hit = log["runs"][0]["results"][0]
            self.assertEqual(hit["ruleId"], "R13.1")
            self.assertEqual(hit["locations"][0]["physicalLocation"]["region"]["startLine"], 2)
            self.assertEqual(len(log["runs"][0]["tool"]["driver"]["rules"]), 122)

    def test_diff_mode_flags_only_the_lines_added_against_the_base(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            write(d, "src/old.ts", SECRET_LINE)    # already on main: not this change's problem
            git(d, "add", ".")
            git(d, "commit", "-q", "-m", "base")
            self.assertEqual(run_cli(d, "scan", "--diff", "main").returncode, 0)
            write(d, "src/new.ts", CLEAN_LINE + SECRET_LINE)
            write(d, "src/old.ts", SECRET_LINE + "eval('2 + 2');\n")
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
