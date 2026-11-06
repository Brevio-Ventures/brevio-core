# Precision of `brevio-core scan` on open-source repositories

<!-- Generated from precision.json. -->

Run on 2026-11-06. The scanner checked 10 pinned repositories: 19,126 files and 3,350,731 lines. It reported 1,606 hits.

## Results

Precision is the share of sampled hits that are real problems. Up to 20 hits per rule were drawn at random (seeded), then read in their code.

| Rule | What it checks | Hits | Sampled | True | False | Precision |
|---|---|---|---|---|---|---|
| R2.8 | No unsafe code or HTML sinks: no eval or new Function on strings; dangerouslySetInnerHTML only with sanitised HTML | 57 | 20 | 20 | 0 | 100% |
| R5.4 | No silent exception swallowing: log or surface errors; never use empty catch blocks | 78 | 20 | 15 | 5 | 75% |
| R6.3 | Deterministic condition waits: never use waitForTimeout/sleep in tests | 135 | 20 | 6 | 14 | 30% |
| R9.1 | No untyped escape hatches: no `as any` casts or `z.any()` schemas in production source | 987 | 20 | 20 | 0 | 100% |
| R9.2 | No silenced type errors: no @ts-ignore; every @ts-expect-error states its reason | 334 | 20 | 20 | 0 | 100% |
| R13.1 | Zero secret logging: redact passwords, tokens, API keys, and authorization headers | 0 | 0 | 0 | 0 | not judged |
| R18.1 | Meaningful image alternative text: informative images supply descriptive alt attribute | 8 | 8 | 7 | 1 | 88% |
| R18.5 | No click handlers on non-interactive elements: divs/spans with onClick specify role='button' | 7 | 7 | 6 | 1 | 86% |
| All | | 1,606 | 115 | 94 | 21 | |

**These verdicts are one reviewer's judgement**, made by reading each sampled hit in its code. Each verdict and its one-line reason is recorded so anyone can check or dispute them. A small sample gives a rough figure, not an exact one.

## Review

Rules whose sampled precision is below 70%: R6.3.

| Rule | Review |
|---|---|
| R2.8 | New ID: these findings carried R2.5, whose title is the SSRF and timeout guard. Kept `stable`. Fixed: vendored folders, minified files and bundles are skipped; TypeScript declaration files (`.d.ts`, `.d.mts`, `.d.cts`) are skipped; test fixture assets are skipped; static literal eval probes in test files are skipped; and `dangerouslySetInnerHTML` with sanitizers (`escapeHtml`, `DOMPurify.sanitize`, `sanitizeHtml`) is accepted (2026-11-06). Precision reached 100% on the judged sample. |
| R5.4 | Kept. Fixed: vendored folders, minified files and bundles are skipped. Left: unminified React and Vue builds that one repository keeps as test assets in a folder with another name; a project excludes them with `exclude` in brevio-core.toml. |
| R6.3 | Preview: it reports and never fails a scan. Most hits are deliberate waits in a browser-automation project's own tests (checking that nothing happens in a given time) and test sources written as strings. No small pattern fix is clearly correct: flagging a sleep only before an assertion that already waits would keep few of the real hits. Candidate for the maintainer to narrow or retire. |
| R9.1 | Kept. Fixed: comment lines no longer match. |
| R9.2 | Kept. Since declaration files are skipped (2026-11-06), three `@ts-ignore` comments in one Playwright `.d.ts` are no longer reported. |
| R13.1 | Rewritten: it flags known credential formats, a JWT, or a random-looking value bound to a secret, token, password or API key name, and leaves placeholders, public and publishable names, Stripe `pk_` keys and Algolia or DocSearch keys alone. It has no hit on this corpus, so no precision: the corpus holds no hard-coded credential. Its earlier false positives (public search keys, a storage entry name) are tests now. |
| R18.1 | Kept. Fixed: comment lines and test files are skipped. Left: a block-comment line that does not start with an asterisk. |
| R18.5 | Kept. Fixed: test files, and a handler that only stops propagation, are skipped. |

## Before and after the rule fixes

Before: the run of 2026-11-05. After: this run. Same corpus, same seed.

| Rule | Hits before | Hits after | Precision before | Precision after |
|---|---|---|---|---|
| R2.8 (was R2.5) | 77 | 57 | 60% | 100% |
| R5.4 | 93 | 78 | 55% | 75% |
| R6.3 | 135 | 135 | 30% | 30% |
| R9.1 | 989 | 987 | 100% | 100% |
| R9.2 | 337 | 334 | 100% | 100% |
| R13.1 | 8 | 0 | 0% | not judged |
| R18.1 | 8 | 8 | 88% | 88% |
| R18.5 | 7 | 7 | 86% | 86% |
| All | 1,654 | 1,606 | | |

## Corpus

| Repository | Commit | Licence | Files | Lines | Hits |
|---|---|---|---|---|---|
| vercel/swr | `8148ef012fd5b317d1e8ec2da4b2ca0673f63c0f` | MIT | 267 | 25,599 | 21 |
| shadcn-ui/ui | `8a3536678a528cc012b9e62484290e79d0be410f` | MIT | 4,506 | 612,035 | 14 |
| TanStack/query | `284abac02d34f88ceb119c2af3fd3cf400b64a7a` | MIT | 2,709 | 281,038 | 89 |
| TanStack/table | `c14e0221b1e656c7bb35e7b3d4cdf188719a3599` | MIT | 4,783 | 548,772 | 297 |
| trpc/trpc | `6ea3d9873854564198c077df20a1db2f01bc2ae3` | MIT | 1,267 | 170,751 | 153 |
| facebook/lexical | `dfe058a840e35e1e796bc69ad2335703b004502e` | MIT | 2,087 | 671,889 | 69 |
| microsoft/playwright | `5c55bfa2c7a65962eebdaa60c6a51cbd230305f0` | Apache-2.0 | 1,970 | 588,630 | 750 |
| excalidraw/excalidraw | `7ded689cad49331167e29fd88b38f38d3736d576` | MIT | 723 | 231,523 | 117 |
| remix-run/react-router | `db80dda076ec9cdcefff480079252fe0c977710e` | MIT | 759 | 209,868 | 82 |
| pmndrs/zustand | `382d29c485e67018c06e75ec7235130d0968522c` | MIT | 55 | 10,626 | 14 |
| All | | | 19,126 | 3,350,731 | 1,606 |

## Method

- The scanner is `brevio-core scan --fail-on all .`. It skips dependencies, build output, vendored folders, minified files and bundles. No rule reads a TypeScript declaration file (`.d.ts`).
- Each repository is fetched shallowly at its pinned commit into a local directory. Its licence file is checked against the corpus.
- The sample is drawn per rule with the seed `e35` from the hits in a fixed order, so the same hits give the same sample. Each sampled hit is stored with 3 lines of context on each side.
- Python 3.12.3.

## Reproduce

```sh
# clone each pinned repository at its commit
git clone --depth 1 <repository>
# run brevio-core scan
brevio-core scan --fail-on all .
```
