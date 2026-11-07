"""brevio-core-assist against a fake endpoint on this machine: what it sends, when it sends, and what it keeps back.

Standard library only. Run from the plugin folder with the plugin and brevio-core importable, for example
``PYTHONPATH=.:.. python -m unittest discover -s tests`` in a release tree.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlunsplit

from brevio_core_assist import assist

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "test-" + os.urandom(12).hex()        # made at run time: no key is written in the tree
SOURCE = "const before = 1;\n// @ts-ignore\nconst after = 2;\n"
FINDING = "src/api.ts:2: [R9.2] `@ts-ignore` used; use `@ts-expect-error` with explanatory reason"


class FakeEndpoint:
    """A local HTTP endpoint that records each request and answers in the shape asked for (or with ``status``)."""

    def __init__(self, fmt: str = "chat", status: int = 200, reply_text: str = "Use @ts-expect-error."):
        self.requests: list[dict] = []
        self.reply_text = reply_text
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                fake.requests.append({"path": self.path, "body": body,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}})
                reply = ({"content": [{"type": "text", "text": fake.reply_text}]} if fmt == "messages"
                         else {"choices": [{"message": {"content": fake.reply_text}}]})
                data = json.dumps(reply if status == 200 else {"error": "refused"}).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("localhost", 0), Handler)
        self.url = urlunsplit(("http", f"localhost:{self.server.server_address[1]}", "/v1/answer", "", ""))
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AssistCase(unittest.TestCase):
    fmt = "chat"
    status = 200

    def setUp(self):
        self.endpoint = FakeEndpoint(self.fmt, self.status)
        self.addCleanup(self.endpoint.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        os.makedirs(os.path.join(self.root, "src"))
        with open(os.path.join(self.root, "src", "api.ts"), "w", encoding="utf-8") as fh:
            fh.write(SOURCE)
        self.env = {"BREVIO_ASSIST_URL": self.endpoint.url, "BREVIO_ASSIST_FORMAT": self.fmt,
                    "BREVIO_ASSIST_MODEL": "local-model", "BREVIO_ASSIST_KEY_ENV": "MY_ENDPOINT_KEY",
                    "MY_ENDPOINT_KEY": KEY}

    def run_cli(self, *argv, env=None, ask=None):
        out, err = io.StringIO(), io.StringIO()
        orig_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("")
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = assist.main([*argv, "--root", self.root], env=self.env if env is None else env, ask=ask)
        finally:
            sys.stdin = orig_stdin
        return code, out.getvalue(), err.getvalue()


class TestOffUntilConfigured(AssistCase):
    def test_it_is_off_without_a_url_a_format_a_model_a_key_name_or_a_key(self):
        for missing in ("BREVIO_ASSIST_URL", "BREVIO_ASSIST_FORMAT", "BREVIO_ASSIST_MODEL", "BREVIO_ASSIST_KEY_ENV",
                        "MY_ENDPOINT_KEY"):
            env = {k: v for k, v in self.env.items() if k != missing}
            code, out, err = self.run_cli("explain", FINDING, "--yes", env=env)
            self.assertEqual(code, assist.EXIT_OFF, missing)
            self.assertIn("off", err)
        self.assertEqual(self.endpoint.requests, [])

    def test_plain_http_to_another_machine_is_refused_before_anything_is_read(self):
        env = dict(self.env, BREVIO_ASSIST_URL=urlunsplit(("http", "example.invalid", "/v1", "", "")))
        code, _out, err = self.run_cli("explain", FINDING, "--yes", env=env)
        self.assertEqual(code, assist.EXIT_OFF)
        self.assertIn("https", err)


class TestWhatIsSent(AssistCase):
    def test_explain_sends_the_rule_text_and_the_one_line_and_shows_that_body_first(self):
        code, out, err = self.run_cli("explain", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_OK, err)
        self.assertEqual(len(self.endpoint.requests), 1)
        sent = self.endpoint.requests[0]
        user = sent["body"]["messages"][-1]["content"]
        self.assertIn("// @ts-ignore", user)
        self.assertIn("R9.2", user)
        for kept in ("const before", "const after", "src/api.ts", self.root):
            self.assertNotIn(kept, json.dumps(sent["body"]))
        shown = out.split("\n\n", 1)[1].rsplit("\n\n", 1)[0]
        self.assertEqual(json.loads(shown), sent["body"])          # what was shown is what was sent
        self.assertEqual(sent["headers"]["authorization"], f"Bearer {KEY}")
        self.assertNotIn(KEY, out + err)
        self.assertIn("Use @ts-expect-error.", out)

    def test_suggest_fix_asks_for_a_corrected_line(self):
        code, _out, _err = self.run_cli("suggest-fix", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_OK)
        self.assertIn("corrected", self.endpoint.requests[0]["body"]["messages"][-1]["content"])

    def test_verify_fix_asks_for_corrected_single_line(self):
        self.endpoint.reply_text = "// @ts-expect-error fixed reason"
        code, _out, _err = self.run_cli("verify-fix", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_OK)
        user = self.endpoint.requests[0]["body"]["messages"][-1]["content"]
        self.assertIn("Return only the corrected single line of code", user)

    def test_verify_fix_verified_exits_0(self):
        self.endpoint.reply_text = "// @ts-expect-error fixed reason"
        code, out, err = self.run_cli("verify-fix", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_OK, err)
        self.assertIn("// @ts-expect-error fixed reason", out)
        self.assertIn("verified: passes [R9.2]", out)
        self.assertEqual(err, "")

    def test_verify_fix_unverified_exits_1(self):
        self.endpoint.reply_text = "// @ts-ignore still broken"
        code, out, err = self.run_cli("verify-fix", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_FAILED)
        self.assertIn("// @ts-ignore still broken", out)
        self.assertIn("unverified: still triggers [R9.2]", err)

    def test_verify_replacement_strips_fences_and_checks_scanner(self):
        finding = assist.parse_finding(FINDING)
        candidate, ok = assist.verify_replacement(finding, "```ts\n// @ts-expect-error fixed reason\n```")
        self.assertEqual(candidate, "// @ts-expect-error fixed reason")
        self.assertTrue(ok)

        candidate, ok = assist.verify_replacement(finding, "Here is the fix:\n```ts\n// @ts-ignore still broken\n```")
        self.assertEqual(candidate, "// @ts-ignore still broken")
        self.assertFalse(ok)

        candidate, ok = assist.verify_replacement(finding, "```ts\n```")
        self.assertEqual(candidate, "")
        self.assertFalse(ok)

        surface_finding = assist.Finding("src/Card.tsx", 12, "R1.1")
        candidate, ok = assist.verify_replacement(surface_finding, '<div className="blur-[120px]">')
        self.assertFalse(ok)
        candidate, ok = assist.verify_replacement(surface_finding, '<div className="blur-none md:blur-[120px]">')
        self.assertTrue(ok)

        candidate, ok = assist.verify_replacement(finding, "  // @ts-ignore still bad")
        self.assertEqual(candidate, "  // @ts-ignore still bad")
        self.assertFalse(ok)

    def test_without_yes_it_asks_and_a_no_sends_nothing(self):
        questions = []
        code, out, _err = self.run_cli("explain", FINDING, ask=lambda q: questions.append(q) or "n")
        self.assertEqual((code, len(questions), self.endpoint.requests), (assist.EXIT_OFF, 1, []))
        self.assertIn("// @ts-ignore", out)

    def test_a_yes_answer_sends_it(self):
        code, _out, _err = self.run_cli("explain", FINDING, ask=lambda q: "y")
        self.assertEqual((code, len(self.endpoint.requests)), (assist.EXIT_OK, 1))

    def test_with_no_terminal_and_no_yes_it_does_not_send(self):
        code, _out, err = self.run_cli("explain", FINDING)
        self.assertEqual((code, self.endpoint.requests), (assist.EXIT_OFF, []))
        self.assertIn("--yes", err)

    def test_a_dry_run_prints_the_request_and_sends_nothing(self):
        code, out, _err = self.run_cli("explain", FINDING, "--dry-run")
        self.assertEqual((code, self.endpoint.requests), (assist.EXIT_OK, []))
        self.assertIn('"model": "local-model"', out)

    def test_a_line_that_is_not_a_finding_or_a_missing_line_is_a_usage_error(self):
        for finding in ("src/api.ts: something", "src/api.ts:9: [R9.2] gone", "src/none.ts:1: [R9.2] x",
                        "src/api.ts:2: [R99.9] no such rule"):
            code, _out, _err = self.run_cli("explain", finding, "--yes")
            self.assertEqual(code, assist.EXIT_USAGE, finding)
        self.assertEqual(self.endpoint.requests, [])


class TestTheMessagesShape(AssistCase):
    fmt = "messages"

    def test_the_messages_shape_sends_its_key_header_the_extra_header_and_reads_its_answer(self):
        env = dict(self.env, BREVIO_ASSIST_HEADER="X-Endpoint-Version: 2024-01-01")
        code, out, err = self.run_cli("explain", FINDING, "--yes", env=env)
        self.assertEqual(code, assist.EXIT_OK, err)
        sent = self.endpoint.requests[0]
        self.assertEqual((sent["headers"]["x-api-key"], sent["headers"]["x-endpoint-version"]), (KEY, "2024-01-01"))
        self.assertNotIn("authorization", sent["headers"])
        self.assertIn("system", sent["body"])
        self.assertIn("Use @ts-expect-error.", out)


class TestAnEndpointThatFails(AssistCase):
    status = 500

    def test_an_endpoint_error_fails_with_the_status_and_never_shows_the_key(self):
        code, out, err = self.run_cli("explain", FINDING, "--yes")
        self.assertEqual(code, assist.EXIT_FAILED)
        self.assertIn("HTTP 500", err)
        self.assertNotIn(KEY, out + err)


class TestNoSdk(unittest.TestCase):
    def test_the_plugin_imports_only_the_standard_library_and_brevio_core(self):
        folder = os.path.join(PLUGIN, "brevio_core_assist")
        foreign = []
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), name)
            for node in ast.walk(tree):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                foreign += [f"{name}: {m}" for m in mods
                            if m.split(".")[0] not in sys.stdlib_module_names and m != "__future__"
                            and m.split(".")[0] not in ("brevio", "brevio_core_assist")]
        self.assertEqual(foreign, [])


class TestAssistHeal(AssistCase):
    def test_assist_heal_clean_workspace(self):
        with open(os.path.join(self.root, "src", "api.ts"), "w", encoding="utf-8") as fh:
            fh.write("export const add = (a: number, b: number): number => a + b;\n")
        code, out, _err = self.run_cli("heal", "--yes")
        self.assertEqual(code, assist.EXIT_OK)
        self.assertIn("workspace is clean", out)
        self.assertEqual(self.endpoint.requests, [])

    def test_assist_heal_needs_repair_sends_heal_packet(self):
        code, out, _err = self.run_cli("heal", "--yes")
        self.assertEqual(code, assist.EXIT_OK)
        self.assertEqual(len(self.endpoint.requests), 1)
        sent = self.endpoint.requests[0]
        self.assertIn("brevio_heal_packet", json.dumps(sent["body"]))
        self.assertIn("Use @ts-expect-error.", out)


if __name__ == "__main__":
    unittest.main()
