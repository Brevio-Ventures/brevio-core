"""Unit tests for brevio-core heal (Pillar 2: Autonomous Self-Healing Loop).

Standard library and exported brevio modules only. Zero forbidden words, no dynamic network code.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from brevio.pipeline import core_heal

AWS_KEY_SAMPLE = "const apiKey = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "';\n"
REQUESTS_SAMPLE = "import requests\nresp = requests.get(url)\n"
CLEAN_SAMPLE = "export const add = (a: number, b: number): number => a + b;\n"
CONFLICT_SAMPLE = "<<<<<<< HEAD\nconst a = 1;\n=======\nconst a = 2;\n>>>>>>> main\n"


class TestCoreHeal(unittest.TestCase):
    def test_run_heal_autofixes_deterministic_rule_r101(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "fetcher.py")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(REQUESTS_SAMPLE)

            res = core_heal.run_heal(root=d, apply_fixes=True)
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "clean")
            self.assertEqual(res["auto_fixed_count"], 1)
            self.assertIn("fetcher.py", res["auto_fixed_files"])
            self.assertEqual(res["remaining_findings"], [])
            self.assertEqual(res["gate_failures"], [])
            self.assertEqual(res["heal_packet"], "")

            with open(src_file, encoding="utf-8") as fh:
                fixed_content = fh.read()
            self.assertIn("timeout=30", fixed_content)

            text_output = core_heal.format_heal_text(res)
            self.assertIn("✅ Self-heal complete: 0 remaining findings", text_output)
            self.assertIn("1 auto-fixed", text_output)

    def test_run_heal_unfixable_rule_violation_returns_needs_repair(self):
        with tempfile.TemporaryDirectory() as d:
            secret_file = os.path.join(d, "secret.ts")
            with open(secret_file, "w", encoding="utf-8") as fh:
                fh.write(AWS_KEY_SAMPLE)

            res = core_heal.run_heal(root=d, apply_fixes=True)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "needs_repair")
            self.assertEqual(res["auto_fixed_count"], 0)
            self.assertTrue(any("[R13.1]" in f for f in res["remaining_findings"]))
            self.assertIn("secret.ts", res["implicated_files"])

            packet = res["heal_packet"]
            self.assertIn("<brevio_heal_packet>", packet)
            self.assertIn("<<<<<<< SEARCH", packet)
            self.assertIn("=======", packet)
            self.assertIn(">>>>>>> REPLACE", packet)
            self.assertIn("</brevio_heal_packet>", packet)

            formatted = core_heal.format_heal_text(res)
            self.assertEqual(formatted, packet)

    def test_run_heal_apply_fixes_false_keeps_deterministic_finding(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "client.py")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(REQUESTS_SAMPLE)

            res = core_heal.run_heal(root=d, apply_fixes=False)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "needs_repair")
            self.assertEqual(res["auto_fixed_count"], 0)
            self.assertTrue(any("[R10.1]" in f for f in res["remaining_findings"]))

            with open(src_file, encoding="utf-8") as fh:
                self.assertNotIn("timeout=30", fh.read())

    def test_run_heal_gate_failure_conflict_marker(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "merge.ts")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(CONFLICT_SAMPLE)

            res = core_heal.run_heal(root=d, apply_fixes=True)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "needs_repair")
            self.assertTrue(len(res["gate_failures"]) > 0 or len(res["remaining_findings"]) > 0)
            self.assertIn("<brevio_heal_packet>", res["heal_packet"])
            self.assertIn("<<<<<<< SEARCH", res["heal_packet"])

    def test_main_json_clean_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "clean.ts")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(CLEAN_SAMPLE)

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = core_heal.main(["--root", d, "--json"])

            self.assertEqual(exit_code, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["ok"])
            self.assertEqual(data["status"], "clean")

    def test_main_json_needs_repair_exits_1(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "secret.ts")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(AWS_KEY_SAMPLE)

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = core_heal.main(["--root", d, "--json"])

            self.assertEqual(exit_code, 1)
            data = json.loads(out.getvalue())
            self.assertFalse(data["ok"])
            self.assertEqual(data["status"], "needs_repair")
            self.assertIn("<brevio_heal_packet>", data["heal_packet"])

    def test_main_format_text_output(self):
        with tempfile.TemporaryDirectory() as d:
            src_file = os.path.join(d, "req.py")
            with open(src_file, "w", encoding="utf-8") as fh:
                fh.write(REQUESTS_SAMPLE)

            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = core_heal.main(["--root", d, "--format", "text"])

            self.assertEqual(exit_code, 0)
            self.assertIn("✅ Self-heal complete", out.getvalue())

    def test_constants_contract(self):
        self.assertEqual(core_heal.EXIT_OK, 0)
        self.assertEqual(core_heal.EXIT_BLOCK, 1)
        self.assertEqual(core_heal.MAX_HEAL_PACKET_CHARS, 6000)


if __name__ == "__main__":
    unittest.main()
