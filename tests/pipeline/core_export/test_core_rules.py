"""Tests that ship with the portable rule engines (ROADMAP 8.2 item 2, Stage 1A).

They import only the standard library and the exported modules, so the exporter can copy them beside the code
and they run unchanged in the exported tree: ``python -m unittest discover -s tests/pipeline/core_export``.
"""
import os
import subprocess
import tempfile
import unittest

from brevio.growth.geo_audit import rubric
from brevio.pipeline import dev_rules
from brevio.pipeline.code_rules import PR_RULES_122, scan_added_lines_for_rules


class TestCodeRules(unittest.TestCase):
    def test_the_catalogue_holds_122_rules_across_r1_to_r19(self):
        self.assertEqual(len(PR_RULES_122), 122)
        for n in range(1, 20):
            self.assertTrue(any(k.startswith(f"R{n}.") for k in PR_RULES_122), n)

    def test_a_planted_secret_and_eval_are_flagged_and_a_clean_file_is_not(self):
        found = scan_added_lines_for_rules({
            "src/a.ts": ["const apiKey = 'fake_secret_key_1234567890abcdef';", "eval('2 + 2');"],
            "src/clean.ts": ["export const add = (a: number, b: number): number => a + b;"],
        })
        self.assertTrue(any("R13.1" in f for f in found))
        self.assertFalse(any("src/clean.ts" in f for f in found))


class TestDevRules(unittest.TestCase):
    def test_the_catalogue_holds_46_rules(self):
        self.assertEqual(len(dev_rules.CATALOG_RULES), 46)

    def test_a_scan_of_a_real_checkout_flags_an_added_as_any_cast(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                               check=True, capture_output=True)
            git("init", "-q", "-b", "main")
            os.makedirs(os.path.join(d, "src"))
            path = os.path.join(d, "src", "a.ts")
            with open(path, "w") as f:
                f.write("export const a = 1;\n")
            git("add", ".")
            git("commit", "-q", "-m", "x")
            with open(path, "w") as f:
                f.write("export const a = 1;\nexport const b = (x as any).y;\n")
            self.assertTrue(dev_rules.scan_added_lines(d, ["src/a.ts"]))


class TestAeoRubric(unittest.TestCase):
    def test_an_empty_page_scores_below_a_discoverable_one(self):
        empty = rubric.score_page(html="<html></html>")
        rich = rubric.score_page(
            html='<html><head><link rel="canonical" href="/"></head><body><h1>Hi</h1>'
                 '<h2>More</h2><script type="application/ld+json">{"@type":"Organization"}</script></body></html>',
            robots_txt="User-agent: *\nAllow: /\n", llms_txt="# X\n> 120 tokens\n")
        self.assertGreater(rich["score"], empty["score"])
        self.assertLessEqual(rich["score"], 100)

    def test_a_blocked_ai_crawler_is_named(self):
        res = rubric.check_robots_txt("User-agent: GPTBot\nDisallow: /\n")
        self.assertIn("GPTBot", res["blocked_bots"])
