"""Unit and CLI tests for brevio-core single-task workflow (connect -> plan -> build -> qa -> pr).

Standard library only. Tested against exported clean-room invariants.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
_RUN = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from brevio.pipeline import core_cli; "
    "raise SystemExit(core_cli.main(sys.argv[2:]))"
)

AWS_KEY_SAMPLE = "const apiKey = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "';\n"
REQUESTS_SAMPLE = "import requests\nresp = requests.get(url)\n"
CLEAN_TS_SAMPLE = "export const add = (a: number, b: number): number => a + b;\n"


def run_cli(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run brevio-core with args in cwd under isolated python -I."""
    return subprocess.run(
        [sys.executable, "-I", "-c", _RUN, ROOT, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def git(d: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def write(d: str, rel: str, text: str) -> None:
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class TestCoreTaskWorkflow(unittest.TestCase):
    def test_connect_and_init_specs_and_undo(self) -> None:
        """Test brevio-core connect and init --specs generating and undo cleanly removing specs."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")

            # 1. brevio-core connect
            r = run_cli(d, "connect")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(d, "CLAUDE.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "CONSTITUTION.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "roadmap.json")))
            self.assertTrue(os.path.isfile(os.path.join(d, ".brevio", "connection.json")))

            with open(os.path.join(d, "roadmap.json"), encoding="utf-8") as fh:
                rd = json.load(fh)
            self.assertEqual(rd.get("edition"), "core")
            self.assertEqual(len(rd.get("items", [])), 3)

            # Clean up spec files for init test
            for fname in ("CLAUDE.md", "CONSTITUTION.md", "roadmap.json"):
                os.remove(os.path.join(d, fname))

            # 2. brevio-core init --specs --yes
            r_init = run_cli(d, "init", "--specs", "--yes")
            self.assertEqual(r_init.returncode, 0, r_init.stderr)
            self.assertTrue(os.path.isfile(os.path.join(d, "CLAUDE.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "CONSTITUTION.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "roadmap.json")))

            # 3. brevio-core init --undo --yes removes them cleanly
            r_undo = run_cli(d, "init", "--undo", "--yes")
            self.assertEqual(r_undo.returncode, 0, r_undo.stderr)
            self.assertFalse(os.path.isfile(os.path.join(d, "CLAUDE.md")))
            self.assertFalse(os.path.isfile(os.path.join(d, "CONSTITUTION.md")))
            self.assertFalse(os.path.isfile(os.path.join(d, "roadmap.json")))

    def test_plan_creates_task_plan_json_and_md(self) -> None:
        """Test brevio-core plan creates .brevio/task_plan.json and TASK_PLAN.md in text and json."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "server.py", "def handle(): pass\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")

            # Text mode
            r = run_cli(d, "plan", "Implement tenant rate limiter")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Implement tenant rate limiter", r.stdout)

            plan_json_path = os.path.join(d, ".brevio", "task_plan.json")
            plan_md_path = os.path.join(d, ".brevio", "TASK_PLAN.md")
            self.assertTrue(os.path.isfile(plan_json_path))
            self.assertTrue(os.path.isfile(plan_md_path))

            with open(plan_json_path, encoding="utf-8") as fh:
                pj = json.load(fh)
            self.assertTrue(pj["ok"])
            self.assertEqual(pj["task"], "Implement tenant rate limiter")

            # JSON mode
            r_json = run_cli(d, "plan", "Implement tenant rate limiter", "--json")
            self.assertEqual(r_json.returncode, 0, r_json.stderr)
            data = json.loads(r_json.stdout)
            self.assertTrue(data["ok"])
            self.assertEqual(data["task"], "Implement tenant rate limiter")
            self.assertIn("server.py", data["target_files"])

    def test_build_autoheals_fixable_finding(self) -> None:
        """Test brevio-core build auto-heals fixable finding and writes BUILD_PACKET.md."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "fetcher.py", REQUESTS_SAMPLE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")

            # Text mode
            r = run_cli(d, "build")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Fixed files: 1", r.stdout)

            packet_path = os.path.join(d, ".brevio", "BUILD_PACKET.md")
            self.assertTrue(os.path.isfile(packet_path))

            with open(os.path.join(d, "fetcher.py"), encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("timeout=30", content)

            # JSON mode
            r_json = run_cli(d, "build", "--json")
            self.assertEqual(r_json.returncode, 0, r_json.stderr)
            data = json.loads(r_json.stdout)
            self.assertTrue(data["ok"])
            self.assertEqual(data["status"], "built")

    def test_qa_fails_on_unfixable_and_passes_on_clean(self) -> None:
        """Test brevio-core qa fails on unfixable findings and passes on clean repo."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "src/key.ts", AWS_KEY_SAMPLE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base")

            # Failing QA run
            r_fail = run_cli(d, "qa")
            self.assertEqual(r_fail.returncode, 1)
            self.assertIn("FAIL", r_fail.stdout)

            report_path = os.path.join(d, ".brevio", "qa_report.json")
            self.assertTrue(os.path.isfile(report_path))
            with open(report_path, encoding="utf-8") as fh:
                rep = json.load(fh)
            self.assertFalse(rep["ok"])
            self.assertGreater(rep["finding_count"], 0)

            # Replace with clean code
            write(d, "src/key.ts", CLEAN_TS_SAMPLE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "clean")

            # Passing QA run
            r_pass = run_cli(d, "qa")
            self.assertEqual(r_pass.returncode, 0, r_pass.stderr)
            self.assertIn("PASS", r_pass.stdout)

            with open(report_path, encoding="utf-8") as fh:
                rep_clean = json.load(fh)
            self.assertTrue(rep_clean["ok"])
            self.assertEqual(rep_clean["finding_count"], 0)

    def test_pr_generates_body_and_marks_roadmap_done(self) -> None:
        """Test brevio-core pr generates PR_BODY.md and updates roadmap.json to done."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "src/math.ts", CLEAN_TS_SAMPLE)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "init")

            # Connect to scaffold roadmap.json
            run_cli(d, "connect")
            run_cli(d, "plan", "TASK-001")

            # Run PR command
            r = run_cli(d, "pr", "--title", "feat: clean task")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("PASS", r.stdout)

            body_path = os.path.join(d, ".brevio", "PR_BODY.md")
            self.assertTrue(os.path.isfile(body_path))
            with open(body_path, encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn("feat: clean task", body)
            self.assertIn("TASK-001", body)
            self.assertIn("Pipeline Receipt", body)

            # Verify roadmap.json updated
            with open(os.path.join(d, "roadmap.json"), encoding="utf-8") as fh:
                rd = json.load(fh)
            self.assertEqual(rd["items"][0]["status"], "done")

    def test_task_full_pipeline_json(self) -> None:
        """Test brevio-core task end-to-end running connect -> plan -> build -> qa -> pr."""
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            write(d, "main.py", "def health(): return {'status': 'ok'}\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "init")

            r = run_cli(d, "task", "Add healthcheck endpoint", "--json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            data = json.loads(r.stdout)
            self.assertTrue(data["ok"])
            self.assertTrue(data["connect"]["ok"])
            self.assertTrue(data["plan"]["ok"])
            self.assertTrue(data["build"]["ok"])
            self.assertTrue(data["qa"]["ok"])
            self.assertTrue(data["pr"]["ok"])

            self.assertTrue(os.path.isfile(os.path.join(d, "CLAUDE.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "CONSTITUTION.md")))
            self.assertTrue(os.path.isfile(os.path.join(d, "roadmap.json")))
            self.assertTrue(os.path.isfile(os.path.join(d, ".brevio", "task_plan.json")))
            self.assertTrue(os.path.isfile(os.path.join(d, ".brevio", "qa_report.json")))
            self.assertTrue(os.path.isfile(os.path.join(d, ".brevio", "PR_BODY.md")))


if __name__ == "__main__":
    unittest.main()
