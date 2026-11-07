# brevio-core 0.9.1

Exported from harness commit `8f5bd18f06ea788102231a12b642ae0e0b7cf32a` of 2026-11-07.

This tree was produced by the harness exporter and checked for leaks before it was written. To reproduce it, check out that commit and run the exporter.

## Rules

No rule was added, changed or retired since the last release.

Notes:

- R2.8 No unsafe code or HTML sinks: no eval or new Function on strings; dangerouslySetInnerHTML only with sanitised HTML: New ID for the eval, new Function and dangerouslySetInnerHTML findings, which builds before 0.6.0 reported as R2.5 (the SSRF and timeout guard, which brevio-core scan does not check); name R2.8 in an ignore comment or brevio-core.toml for them.
- R6.3 Deterministic condition waits: never use waitForTimeout/sleep in tests: Now preview: it reports a sleep in a test but never fails a scan (see its rule page).
