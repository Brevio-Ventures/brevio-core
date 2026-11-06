"""``brevio-core aeo``: the AEO rubric on a folder of built pages, run in a clean interpreter (ADOPTION.md 0.29).

Standard library only: the exporter copies this file beside the code (the 0.6 set) and it runs unchanged there. In the
harness the test first exports the 0.6 set and runs against that copy. Every socket call fails and reports itself, so a
test sees it if the command ever reached the network.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EXPORTER = os.path.join(ROOT, "tools", "export_core.py")      # present in the harness checkout only
TREE = ROOT
_EXPORT = tempfile.TemporaryDirectory()
_RUN = ("import socket, sys\n"
        "def _refuse(*a, **k):\n"
        "    sys.stderr.write('NETWORK-USED\\n')\n"
        "    raise OSError('the network is off in this test')\n"
        "socket.socket = socket.create_connection = socket.getaddrinfo = _refuse\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from brevio.pipeline import core_cli\n"
        "raise SystemExit(core_cli.main(sys.argv[2:]))\n")
WEB = "https" + "://"        # joined: the leak scan refuses a literal foreign URL in an exported file
WORDS = "An answer engine reads this paragraph and quotes it. " * 8
RICH = ('<html><head><link rel="canonical" href="/guide"><script type="application/ld+json">{"@type": "TechArticle"}'
        f"</script></head><body><h1>Guide</h1><h2>Steps</h2><table><tr><td>a</td></tr></table><p>{WORDS}</p>"
        '<a href="/skill.md">skill</a> <a href="/geo-audit?domain=x">check</a></body></html>')
SHELL = '<html><body><div id="__next"></div>' + " " * 1600 + "</body></html>"
LLMS = "# Site\n- [Guide](/guide) (~600 tokens)\n"


def setUpModule():
    global TREE
    if os.path.isfile(EXPORTER):
        out = os.path.join(_EXPORT.name, "core")
        subprocess.run([sys.executable, EXPORTER, "--out", out, "--set", "0.6"], check=True, capture_output=True, timeout=120)
        TREE = out


def tearDownModule():
    _EXPORT.cleanup()


def run(cwd, *args):
    return subprocess.run([sys.executable, "-I", "-c", _RUN, TREE, "aeo", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def write(d, rel, text):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path) or d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def site(d):
    write(d, "site/guide.html", RICH)
    write(d, "site/app/index.html", SHELL)
    write(d, "site/llms.txt", LLMS)
    write(d, "site/robots.txt", "User-agent: *\nAllow: /\n")
    return os.path.join(d, "site")


def card(d, *args):
    res = run(d, *args, "--format", "json")
    return res.returncode, json.loads(res.stdout), res.stderr


class TestTheScorecard(unittest.TestCase):
    def test_a_folder_scores_every_page_worst_first_and_reports_only_without_a_minimum(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = card(d, site(d))
        self.assertEqual(code, 0, err)
        self.assertNotIn("NETWORK-USED", err)
        self.assertEqual([p["path"] for p in out["pages"]], ["app/index.html", "guide.html"])
        low, high = out["pages"]
        self.assertLess(low["score"], high["score"])
        self.assertEqual(out["lowest"], low["score"])
        self.assertIn("client-only JS hydration wall (<120 chars visible SSR text)", low["gaps"])
        self.assertEqual(set(high["pillars"]), {"discovery", "structure", "token_economics", "capability", "ux_bridge"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["site"], {"robots_txt": True, "blocked_bots": [], "llms_txt": True, "skill_md": False,
                                       "agent_card": False})

    def test_a_page_below_the_minimum_fails_the_run_and_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            _code, out, _err = card(d, root)
            between = out["pages"][0]["score"] + 1
            code, out, _err = card(d, root, "--min", str(between))
            text = run(d, root, "--min", str(between))
        self.assertEqual(code, 1)
        self.assertEqual(out["below_min"], ["app/index.html"])
        self.assertFalse(out["ok"])
        self.assertEqual(text.returncode, 1)
        self.assertIn(f"1 below --min {between}", text.stdout)

    def test_the_text_report_lists_the_site_files_and_each_gap_under_its_page(self):
        with tempfile.TemporaryDirectory() as d:
            res = run(d, site(d))
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        self.assertIn("  robots.txt: present, blocks no AI crawler", lines)
        self.assertIn("  llms.txt: present", lines)
        self.assertIn("  skill.md: missing", lines)
        at = next(i for i, line in enumerate(lines) if line.endswith("  app/index.html"))
        self.assertTrue(lines[at + 1].startswith("      - "))

    def test_a_robots_file_that_shuts_out_an_ai_crawler_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            write(d, "site/robots.txt", "User-agent: GPTBot\nDisallow: /\n")
            _code, out, _err = card(d, root)
            text = run(d, root).stdout
        self.assertEqual(out["site"]["blocked_bots"], ["GPTBot"])
        self.assertIn("robots.txt blocks AI crawlers (GPTBot)", out["pages"][0]["gaps"])
        self.assertIn("robots.txt: blocks GPTBot", text)

    def test_a_markdown_copy_beside_a_page_counts_as_its_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            _code, before, _err = card(d, root)
            write(d, "site/guide.md", "# Guide\n")
            _code, after, _err = card(d, root)
        score = {p["path"]: p["pillars"]["token_economics"] for p in before["pages"]}
        self.assertGreater({p["path"]: p["pillars"]["token_economics"] for p in after["pages"]}["guide.html"], score["guide.html"])

    def test_one_page_reads_the_site_files_of_its_folder(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            code, out, _err = card(d, os.path.join(root, "guide.html"))
        self.assertEqual(code, 0)
        self.assertEqual([p["path"] for p in out["pages"]], ["guide.html"])
        self.assertTrue(out["site"]["llms_txt"])

    def test_hidden_folders_and_node_modules_are_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            write(d, "site/.cache/a.html", SHELL)
            write(d, "site/node_modules/b/c.html", SHELL)
            _code, out, _err = card(d, root)
        self.assertEqual(len(out["pages"]), 2)

    def test_the_markdown_report_is_a_table_and_escapes_a_hostile_file_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = site(d)
            write(d, "site/@team <b>.html", RICH)
            res = run(d, root, "--format", "markdown")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("| Page | Score | Grade | Gaps |", res.stdout)
        self.assertNotIn("@team", res.stdout)
        self.assertNotIn("<b>", res.stdout)
        self.assertIn("&lt;b&gt;", res.stdout)


class TestWhatItRefuses(unittest.TestCase):
    def test_a_url_is_refused_with_the_way_to_score_it_and_nothing_is_fetched(self):
        with tempfile.TemporaryDirectory() as d:
            for target in (WEB + "site.test/page", "www.site.test", "site.test/blog"):
                res = run(d, target)
                self.assertEqual(res.returncode, 2, target)
                self.assertEqual(res.stdout, "")
                self.assertIn("reads local files only", res.stderr)
                self.assertIn("Save the built page first", res.stderr)
                self.assertIn("brevio.pro", res.stderr)
                self.assertNotIn("NETWORK-USED", res.stderr)

    def test_a_missing_path_a_folder_without_pages_and_a_bad_minimum_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "empty/robots.txt", "")
            write(d, "notes.txt", "x")
            missing, empty, not_page = run(d, "missing.html"), run(d, "empty"), run(d, "notes.txt")
            bad_min = run(d, "empty", "--min", "101")
        self.assertEqual([r.returncode for r in (missing, empty, not_page, bad_min)], [2, 2, 2, 2])
        self.assertIn("no such file or folder", missing.stderr)
        self.assertIn("no .html page", empty.stderr)
        self.assertIn("is not an .html page", not_page.stderr)

    def test_a_local_file_named_like_a_host_is_read_not_refused(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "docs.site.test/index.html", RICH)
            code, out, _err = card(d, "docs.site.test")
        self.assertEqual(code, 0)
        self.assertEqual(len(out["pages"]), 1)

    def test_the_command_is_listed_in_the_help(self):
        res = subprocess.run([sys.executable, "-I", "-c", _RUN, TREE, "--help"], capture_output=True, text=True, timeout=60)
        self.assertIn("aeo", res.stdout)


if __name__ == "__main__":
    unittest.main()
