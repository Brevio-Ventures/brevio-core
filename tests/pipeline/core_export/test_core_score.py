"""Tests for brevio.pipeline.core_score and its CLI/operator integrations."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from brevio.operator import gain_cmd
from brevio.pipeline import core_cli, core_init, core_score

GITHUB_HTTPS = "https://" + "github.com/"
GITHUB_SSH = "git" + "@" + "github.com:"


class TestCoreScore(unittest.TestCase):
    def test_grade_and_color_buckets(self) -> None:
        self.assertEqual(core_score.grade_and_color(100), ("A+", "brightgreen"))
        self.assertEqual(core_score.grade_and_color(95), ("A", "brightgreen"))
        self.assertEqual(core_score.grade_and_color(85), ("B", "green"))
        self.assertEqual(core_score.grade_and_color(75), ("C", "yellow"))
        self.assertEqual(core_score.grade_and_color(65), ("D", "orange"))
        self.assertEqual(core_score.grade_and_color(59), ("F", "red"))

    def test_detect_repo_slug_env_and_git_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            old_repo = os.environ.get("GITHUB_REPOSITORY")
            try:
                os.environ["GITHUB_REPOSITORY"] = "example-org/widgets"
                self.assertEqual(core_score.detect_repo_slug(d), "example-org/widgets")

                os.environ.pop("GITHUB_REPOSITORY", None)
                git_dir = os.path.join(d, ".git")
                os.makedirs(git_dir, exist_ok=True)
                with open(os.path.join(git_dir, "config"), "w", encoding="utf-8") as fh:
                    fh.write(f'[remote "origin"]\n\turl = {GITHUB_HTTPS}example-org/brevio-core.git\n')
                self.assertEqual(core_score.detect_repo_slug(d), "example-org/brevio-core")

                with open(os.path.join(git_dir, "config"), "w", encoding="utf-8") as fh:
                    fh.write(f'[remote "origin"]\n\turl = {GITHUB_SSH}example-org/repo-name.git\n')
                self.assertEqual(core_score.detect_repo_slug(d), "example-org/repo-name")
            finally:
                if old_repo is not None:
                    os.environ["GITHUB_REPOSITORY"] = old_repo
                else:
                    os.environ.pop("GITHUB_REPOSITORY", None)

    def test_score_clean_file_text_and_roast(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            clean = os.path.join(d, "clean.py")
            with open(clean, "w", encoding="utf-8") as fh:
                fh.write("def add(a: int, b: int) -> int:\n    return a + b\n")

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc = core_score.main([clean, "--roast"])
            out = out_s.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("100/100 (Grade: A+)", out)
            self.assertIn("Zero agent-slop detected", out)
            self.assertIn("[![Agent Safety: A+ (100/100)]", out)
            self.assertIn(core_cli.upgrade_line("score", True), out)

    def test_score_defective_file_min_threshold_and_playground_links(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.py")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(
                    "def swallow():\n"
                    "    try:\n"
                    "        risky()\n"
                    "    except:\n"
                    "        pass\n"
                )

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc = core_score.main([bad, "--min", "95", "--roast", "--no-upgrade-line"])
            out = out_s.getvalue()
            self.assertEqual(rc, 1)
            self.assertIn("90/100 (Grade: A)", out)
            self.assertIn("https://brevio.pro/tools/agent-guard-playground?rule=R5.4", out)
            self.assertIn("R5.4 (No silent exception swallowing)", out)
            self.assertNotIn("https://brevio.pro/teams", out)

    def test_score_badge_only_and_formats(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            clean = os.path.join(d, "clean.py")
            with open(clean, "w", encoding="utf-8") as fh:
                fh.write("def ok() -> int:\n    return 1\n")

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc = core_score.main([clean, "--badge"])
            badge_out = out_s.getvalue()
            self.assertEqual(rc, 0)
            self.assertTrue(badge_out.strip().startswith("[![Agent Safety: A+ (100/100)]("))
            self.assertNotIn("\n", badge_out.strip())

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc_json = core_score.main([clean, "--format", "json"])
            payload = json.loads(out_s.getvalue())
            self.assertEqual(rc_json, 0)
            self.assertEqual(payload["score"], 100)
            self.assertEqual(payload["grade"], "A+")
            self.assertEqual(payload["files"], 1)
            self.assertIn("badge_markdown", payload)
            self.assertIn("receipt_url", payload)

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc_md = core_score.main([clean, "--format", "markdown", "--roast", "--no-upgrade-line"])
            md_out = out_s.getvalue()
            self.assertEqual(rc_md, 0)
            self.assertIn("### Brevio Agent Safety Score: 100/100 (Grade `A+`)", md_out)
            self.assertIn("Zero agent-slop detected", md_out)

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc_md2 = core_score.main([clean, "--markdown", "--roast", "--no-upgrade-line"])
            md_out2 = out_s.getvalue()
            self.assertEqual(rc_md2, 0)
            self.assertIn("### Brevio Agent Safety Score: 100/100 (Grade `A+`)", md_out2)

    def test_core_cli_dispatches_score_and_interactive_menu(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            clean = os.path.join(d, "clean.py")
            with open(clean, "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")

            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                rc = core_cli.main(["score", clean, "--badge"])
            out = out_s.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("[![Agent Safety: A+ (100/100)]", out)

            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO("5\n")
                tools = {"score": lambda argv: 0 if argv == [] else 2}
                out_s = io.StringIO()
                with contextlib.redirect_stdout(out_s):
                    rc_menu = core_cli._interactive_entry(tools)
                menu_out = out_s.getvalue()
                self.assertEqual(rc_menu, 0)
                self.assertIn("[5] Compute Agent Safety Score & README badge (score)", menu_out)
            finally:
                sys.stdin = old_stdin

    def test_gain_cmd_includes_markdown_badge_before_upgrade_line(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            old_cwd = os.getcwd()
            try:
                os.chdir(d)
                out_s = io.StringIO()
                with contextlib.redirect_stdout(out_s):
                    rc = gain_cmd.main([])
                out = out_s.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("Markdown Badge: [![Verified by brevio-core](", out)
                self.assertTrue(out.strip().endswith(core_cli.upgrade_line("gain", True)))
            finally:
                os.chdir(old_cwd)

    def test_core_init_report_includes_score_hint(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rel = core_init.Release(
                repo_url=GITHUB_HTTPS + "example-org/brevio-core",
                version="0.1.0",
            )
            ctx = core_init.Ctx(d, rel, {})
            out_s = io.StringIO()
            with contextlib.redirect_stdout(out_s):
                core_init._report(ctx, [])
            out = out_s.getvalue()
            self.assertIn("Run `brevio-core score` for your live Agent Safety Score (A+ to F) & scorecard.", out)


if __name__ == "__main__":
    unittest.main()
