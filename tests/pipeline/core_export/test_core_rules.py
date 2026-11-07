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

# Fakes in real credential formats, joined at run time so this file is not itself a finding of a secret scan: AWS's
# documented example key ID, and 32 hex characters (the shape of an Algolia search key) made from a fixed seed.
AWS_EXAMPLE = "AKIA" + "IOSFODNN7EXAMPLE"
HEX_KEY = "".join("0123456789abcdef"[(i * 7 + 3) % 16] for i in range(32))


class TestCodeRules(unittest.TestCase):
    def test_the_catalogue_holds_123_rules_across_r1_to_r19(self):
        self.assertEqual(len(PR_RULES_122), 123)      # R2.8 added before the first release (E35, 2026-11-05)
        for n in range(1, 20):
            self.assertTrue(any(k.startswith(f"R{n}.") for k in PR_RULES_122), n)

    def test_a_planted_secret_and_eval_are_flagged_and_a_clean_file_is_not(self):
        found = scan_added_lines_for_rules({
            "src/a.ts": ["const apiKey = '" + "AKIA" + "IOSFODNN7EXAMPLE" + "';", "eval('2 + 2');"],
            "src/clean.ts": ["export const add = (a: number, b: number): number => a + b;"],
        })
        self.assertTrue(any("R13.1" in f for f in found))
        self.assertFalse(any("src/clean.ts" in f for f in found))

    # The false positives the E35 precision run found on open-source repositories (docs/benchmarks/precision.md).

    def test_playwrights_dollar_eval_is_not_javascript_eval(self):
        found = scan_added_lines_for_rules({"tests/page/a.spec.ts": ["expect(await page.$eval('div', e => e.id)).toBe('x');",
                                                                     "await page.$$eval('div', els => els.length);"],
                                            "src/run.ts": ["const v = eval(expr);", "globalThis.eval(code);"]})
        self.assertEqual([f.split(":")[0] for f in found if "[R2.8]" in f], ["src/run.ts", "src/run.ts"])

    def test_sanitized_dangerously_set_inner_html_is_not_flagged(self):
        """R2.8 false positive from remix-run/react-router: escapeHtml at the dangerouslySetInnerHTML sink."""
        found = scan_added_lines_for_rules({
            "packages/react-router/lib/dom/ssr/components.tsx": [
                'dangerouslySetInnerHTML={{ __html: escapeHtml(json) }}',
                'dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(dirty) }}',
                'dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }}',
                'dangerouslySetInnerHTML={{ __html: contextScript }}',
            ],
            "src/component.tsx": [
                'dangerouslySetInnerHTML={{ __html: svgData }}',
            ],
        })
        hits = [f for f in found if "[R2.8]" in f]
        self.assertEqual(len(hits), 2)
        self.assertIn("packages/react-router/lib/dom/ssr/components.tsx:4:", hits[0])
        self.assertIn("src/component.tsx:1:", hits[1])

    def test_static_eval_probe_in_tests_is_not_flagged(self):
        """R2.8 false positives from playwright and react-router: static literal eval probes in test/integration files."""
        found = scan_added_lines_for_rules({
            "tests/library/capabilities.spec.ts": [
                'window.testStatus = eval("\'FAILED\'");',
            ],
            "integration/split-route-modules-test.ts": [
                'return "clientLoader in main chunk: " + eval("typeof inSplittableMainChunk === \'function\'");',
                'return "clientAction in main chunk: " + eval("typeof inUnsplittableMainChunk === \'function\'");',
            ],
            "tests/dynamic.test.ts": [
                'const v = eval(dynamicCode);',
            ],
            "src/run.ts": [
                'const res = eval("2 + 2");',
            ],
        })
        hits = [f for f in found if "[R2.8]" in f]
        self.assertEqual(len(hits), 2)
        self.assertIn("tests/dynamic.test.ts:1:", hits[0])
        self.assertIn("src/run.ts:1:", hits[1])

    def test_vendored_test_assets_are_not_flagged_for_r28(self):
        """R2.8 false positives from playwright: vendored builds in tests/assets."""
        found = scan_added_lines_for_rules({
            "tests/assets/reading-list/vue_2.6.14.js": [
                "new Function('return 1');",
            ],
            "tests/assets/reading-list/vue_3.1.5.js": [
                "const render = (new Function(code)());",
            ],
            "src/compiler.ts": [
                "const fn = new Function('a', 'return a');",
            ],
            "tests/unit/generateNodeJSON.test.ts": [
                "const parsed = new Function(`\"use strict\";\\n${code}`);",
            ],
        })
        hits = [f for f in found if "[R2.8]" in f]
        self.assertEqual(len(hits), 2)
        self.assertIn("src/compiler.ts:1:", hits[0])
        self.assertIn("tests/unit/generateNodeJSON.test.ts:1:", hits[1])

    def test_a_fixture_key_in_a_test_file_is_not_a_hardcoded_secret(self):
        line = "      accessKeyId: '" + AWS_EXAMPLE + "',"
        found = scan_added_lines_for_rules({"src/provider.test.ts": [line], "src/provider.ts": [line]})
        self.assertEqual([f.split(":")[0] for f in found if "[R13.1]" in f], ["src/provider.ts"])

    def test_a_public_search_key_or_a_storage_entry_name_is_not_a_hardcoded_secret(self):
        """The R13.1 false positives of the E35 precision run: Algolia search keys and a local-storage entry name."""
        found = scan_added_lines_for_rules({
            "examples/react/algolia/src/api.ts": ["// From Algolia example", "const ALGOLIA_APP_ID = 'latency'",
                                                  "const ALGOLIA_SEARCH_API_KEY = '" + HEX_KEY + "'"],
            "dev-docs/docusaurus.config.js": ["      algolia: {", '        appId: "8FEAOD28DI",',
                                              '        apiKey: "' + HEX_KEY + '",', '        indexName: "docs",'],
            "packages/common/src/constants.ts": ["export const EDITOR_LS_KEYS = {", '  OAI_API_KEY: "excalidraw-oai-api-key",'],
            "lib/react-dom.js": ["var ReactPropTypesSecret = 'SECRET_DO_NOT_PASS_THIS_OR_YOU_WILL_BE_FIRED';"],
            "src/pay.ts": ["const stripeKey = 'pk_live_' + 'x';", "const publishableKey = '" + HEX_KEY + "';",
                           "const apiKey = 'your-api-key-1234567890';", "const apiKey = process.env.API_KEY;"],
        })
        self.assertEqual([f for f in found if "[R13.1]" in f], [])

    def test_a_credential_format_or_a_random_value_under_a_secret_name_is_a_hardcoded_secret(self):
        lines = {
            "src/aws.ts": "const client = new S3({ accessKeyId: '" + AWS_EXAMPLE + "' });",
            "src/gh.ts": "const gh = new Octokit({ auth: '" + "gh" + "p_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5" + "' });",
            "src/key.ts": "const pem = '-----BEGIN " + "RSA PRIVATE KEY-----';",
            "src/jwt.ts": "const sessionToken = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.example-signature';",
            "src/hex.ts": "const apiKey: string = '" + HEX_KEY + "';",
            "src/conf.py": "CLIENT_SECRET = '" + HEX_KEY + "'",
        }
        found = scan_added_lines_for_rules({path: [line] for path, line in lines.items()})
        self.assertEqual(sorted(f.split(":")[0] for f in found if "[R13.1]" in f), sorted(lines))

    def test_a_comment_that_names_img_or_as_any_or_eval_is_not_code(self):
        found = scan_added_lines_for_rules({"src/App.tsx": [
            "  /** updates image cache for images that fail during <img> element creation */",
            " * The zero-size `<img>` the reconciler parks outside a block",
            "  // we cast the value as any because the type is wrong upstream",
            "// Note: this file should be loadable with eval() into a worker.",
            "  } catch {} // not a comment line: still flagged",
            "  // @ts-ignore",
        ]})
        self.assertEqual(sorted(f.split(" ")[1] for f in found), ["[R5.4]", "[R9.2]"])

    def test_test_only_components_are_not_checked_for_accessibility(self):
        line = "      return <div onClick={() => setIndex(1)}>{data}</div>"
        img = "  <img src={url} />"
        found = scan_added_lines_for_rules({"test/use-swr-cache.test.tsx": [line, img], "src/Page.tsx": [line, img]})
        self.assertEqual(sorted(f.split(" ")[1] for f in found), ["[R18.1]", "[R18.5]"])
        self.assertTrue(all(f.startswith("src/Page.tsx") for f in found))

    def test_a_div_that_only_stops_click_propagation_is_not_a_control(self):
        found = scan_added_lines_for_rules({"src/Filter.tsx": [
            '    <div className="column-filter" onClick={(e) => e.stopPropagation()}>',
            "    <div onClick={e => e.stopPropagation()}>",
            '    <div className="close" onClick={onClose}>',
        ]})
        self.assertEqual([f.split(":")[1] for f in found if "[R18.5]" in f], ["3"])

    def test_a_typescript_declaration_file_gives_no_finding(self):
        """The R2.8 false positive of the E35 precision run: prose in a doc comment of Playwright's protocol.d.ts,
        on a line that does not start with an asterisk. A declaration holds no code that runs (2026-11-06)."""
        comment = ["      replMode?: boolean;", "      /**",
                   "       * The Content Security Policy (CSP) for the target might block 'unsafe-eval'",
                   "which includes eval(), Function(), setTimeout() and setInterval()",
                   "when called with non-callable arguments. This flag bypasses CSP for this", "       */"]
        found = scan_added_lines_for_rules({
            "packages/playwright-core/types/protocol.d.ts": comment,
            "utils/overrides.d.ts": ["// @ts-ignore this will be any if zod is not installed"],
            "types/index.d.mts": ["const apiKey = '" + AWS_EXAMPLE + "';"],
            "types/index.d.cts": ["const apiKey = '" + AWS_EXAMPLE + "';"],
            "src/protocol.ts": comment,
        })
        self.assertEqual([f.split(":")[0] for f in found], ["src/protocol.ts"])

    def test_promoted_rules_r55_r101_r162_and_r182_flag_bad_patterns_and_pass_clean_code(self):
        found = scan_added_lines_for_rules({
            "src/runner.py": [
                "subprocess.run(cmd, shell=True)",
                'os.system(f"rm -rf {target}")',
                'subprocess.run(["git", "status"], timeout=30, check=True)',
            ],
            "tests/test_runner.py": [
                "subprocess.run(cmd, shell=True)",
            ],
            "src/client.py": [
                "res = requests.get(url)",
                "res = requests.post(url, json=payload, timeout=10)",
            ],
            "package.json": [
                '  "version": "*",',
                '  "private": "*",',
                '  "left-pad": "*",',
                '  "lodash": "latest",',
                '  "zod": "3.22.4"',
            ],
            "src/Link.tsx": [
                '<a href="/docs" target="_blank">Docs</a>',
                '<a href="/docs" target="_blank" rel="noopener noreferrer">Docs</a>',
            ],
        })
        self.assertEqual([f.split(":")[1] for f in found if "[R5.5]" in f], ["1", "2"])
        self.assertEqual([f.split(":")[1] for f in found if "[R10.1]" in f], ["1"])
        self.assertEqual([f.split(":")[1] for f in found if "[R16.2]" in f], ["3", "4"])
        self.assertEqual([f.split(":")[1] for f in found if "[R18.2]" in f], ["1"])

    def test_r28_flags_raw_sql_interpolation_and_bidi_control_chars_and_r131_flags_client_env_secrets(self):
        bidi = "const isAdmin = false; // \u202e } \u2066if (isAdmin)\u2069"
        found = scan_added_lines_for_rules({
            "src/db.py": [
                'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")',
                'cursor.execute("SELECT * FROM users WHERE id = %s", (uid,))',
            ],
            "src/repo.ts": [
                "await prisma.$queryRawUnsafe(`SELECT * FROM orders WHERE id = ${orderId}`);",
                bidi,
            ],
            "src/env.ts": [
                "const key = process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;",
                "const db = import.meta.env.VITE_DATABASE_URL;",
                "const pub = process.env.NEXT_PUBLIC_APP_URL;",
            ],
        })
        r28 = [f"{f.split(':')[0]}:{f.split(':')[1]}" for f in found if "[R2.8]" in f]
        r131 = [f"{f.split(':')[0]}:{f.split(':')[1]}" for f in found if "[R13.1]" in f]
        self.assertEqual(r28, ["src/db.py:1", "src/repo.ts:1", "src/repo.ts:2"])
        self.assertEqual(r131, ["src/env.ts:1", "src/env.ts:2"])


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
