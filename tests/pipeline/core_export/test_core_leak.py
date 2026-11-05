"""The generic leak checks hold for the tree this file sits in (ROADMAP E13).

Standard library only, so it runs in the public repository's CI too: no URL outside the project, its GitHub
organisation and documentation sites; no email but a placeholder or the published security address; no path or module
of the private harness that is not in the tree.
"""
import os
import tempfile
import unittest

from brevio.pipeline import leak_scan

# The planted leaks are built from pieces so that this file, which the scan also reads, holds none of them.
HTTPS, HTTP = "https" + "://", "http" + "://"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


HARNESS = os.path.exists(os.path.join(ROOT, "tools", "export_core.py"))


@unittest.skipIf(HARNESS, "the harness checkout is not the public tree; its test runs this file on an export")
class TestTreeIsClean(unittest.TestCase):
    def test_this_tree_has_no_stray_url_email_or_internal_path(self):
        self.assertEqual(leak_scan.scan_tree(ROOT), [])


class TestChecks(unittest.TestCase):
    def test_only_project_organisation_and_documentation_urls_pass(self):
        ok = f"https://brevio.pro/x {HTTPS}GitHub.com/Example-Org/repo https://docs.python.org/3/"
        self.assertEqual(leak_scan.bad_urls(ok, "example-org"), [])
        self.assertEqual(len(leak_scan.bad_urls(f"{HTTPS}github.com/example-org/repo")), 1)   # no organisation named
        bad = leak_scan.bad_urls(f"see {HTTPS}github.com/someone/else and {HTTP}intranet.example.org:8080/admin", "example-org")
        self.assertEqual(len(bad), 2)

    def test_a_lookalike_host_is_not_the_project_host(self):
        lookalikes = [f"{HTTPS}notbrevio.pro/", f"{HTTPS}brevio.pro.evil.example/"]
        self.assertEqual(leak_scan.bad_urls(" ".join(lookalikes)), lookalikes)

    def test_only_placeholder_and_the_security_address_pass_as_email(self):
        self.assertEqual(leak_scan.bad_emails("a@example.com security@brevio.pro"), [])
        stray = "jane" + "@corp.io"
        self.assertEqual(leak_scan.bad_emails(stray), [stray])

    def test_a_module_or_path_that_is_not_in_the_tree_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "brevio", "pipeline"))
            for rel in ("brevio/__init__.py", "brevio/pipeline/__init__.py"):
                with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
                    fh.write('"""Part of the portable brevio rule engines."""\n')
            with open(os.path.join(d, "brevio", "pipeline", "dev_rules.py"), "w", encoding="utf-8") as fh:
                fh.write("X = 1\n")
            private = ["brevio" + ".pipeline.gates", "tools" + "/x.py"]
            text = "brevio.pipeline.dev_rules.X, brevio/pipeline/dev_rules.py, brevio.pro, " + ", ".join(private)
            self.assertEqual(leak_scan.bad_internal_paths(text, d), private)


if __name__ == "__main__":
    unittest.main()
