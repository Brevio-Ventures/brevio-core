"""122 PR-Checkable Zero-Token Code Rules Engine (R1–R19).

Pure deterministic AST/regex rule catalog and pre-commit / PR diff scanner.
Contains zero tenant-derived IP or markers (100% portable for brevio-gate).
"""
from __future__ import annotations

import os
import re

# 122 PR-Checkable Zero-Token Engineering Rules Catalog (R1–R19)
PR_RULES_122: dict[str, str] = {
    # R1: UI / Mobile Performance (8 rules)
    "R1.1": "Mobile GPU budget: scope blur >=40px to md:/lg: desktop viewports",
    "R1.2": "SSR visibility resilience: never leave [data-reveal] at opacity:0 without CSS animation fallback",
    "R1.3": "Third-party script deferral: load GTM/GA4 with lazyOnload after hydration",
    "R1.4": "Zero-flash theme bootstrap: paired semantic tokens across light/dark modes",
    "R1.5": "No dead controls: every interactive element wires a handler and loading/error feedback",
    "R1.6": "Accessible switch geometry: inline-flex items-center shrink-0 on toggle tracks",
    "R1.7": "LCP asset priority: priority/fetchpriority=high on hero LCP image, lazy below fold",
    "R1.8": "Async polling hygiene: clear intervals on unmount and stop polling on terminal states",
    # R2: Security & Tenancy (7 rules)
    "R2.1": "Tenant context derivation: derive tenant context from verified session, never client payload",
    "R2.2": "Tenant-scoped data access: every DB read/write filters by authenticated workspace scope",
    "R2.3": "Dual-key entity resolution: discriminate UUID/CUID vs domain/slug before database query",
    "R2.4": "Raw-body webhook verification: verify HMAC against raw request text before JSON parse",
    "R2.5": "Outbound SSRF & timeout guard: validate URL host and set AbortSignal.timeout()",
    "R2.6": "Constant-time secret comparison: use timingSafeEqual / compare_digest",
    "R2.7": "Secure cookie & CORS hygiene: HttpOnly, Secure, SameSite, no wildcard CORS with credentials",
    # R3: Billing & FinOps (5 rules)
    "R3.1": "Idempotent webhook processing: deduplicate event_id with monotonic state transitions",
    "R3.2": "Monetary integer representation: store money as integer minor units (cents) + currency",
    "R3.3": "Gateway ID discrimination: validate customer/subscription/checkout prefix before API call",
    "R3.4": "Pre-execution quota enforcement: verify tier entitlement before paid LLM/API calls",
    "R3.5": "Transactional outbox: persist DB state before enqueuing external side effects",
    # R4: Database & Migrations (5 rules)
    "R4.1": "Expand-contract migrations: additive nullable/default columns; no single-step drop/rename",
    "R4.2": "Foreign-key & tenant composite indexing: index FKs and (tenant_id, created_at)",
    "R4.3": "N+1 query prevention: batch queries with IN / joins instead of per-row loop queries",
    "R4.4": "Ingestion FK pre-resolution: upsert or verify parent workspace before child rows",
    "R4.5": "Bounded pagination: enforce hard LIMIT (<=100) on every list query",
    # R5: Reliability & Fallbacks (5 rules)
    "R5.1": "Deterministic graceful fallbacks: return explicit degraded status, never fabricated metrics",
    "R5.2": "HTTP empty-body hygiene: 204 returns empty body; 200 JSON sets Content-Type",
    "R5.3": "Bounded retry with jitter: retry only transient 429/502/503/504 with backoff + jitter",
    "R5.4": "No silent exception swallowing: log or surface errors; never use empty catch blocks",
    "R5.5": "Process & lock safety: every subprocess.run carries timeout=; locks use try/finally",
    # R6: Testing & Hermeticity (5 rules)
    "R6.1": "Real production import gate: tests must import and invoke real production code",
    "R6.2": "Mutation side-effect assertions: assert persisted state or DOM changes, not just HTTP 200",
    "R6.3": "Deterministic condition waits: never use waitForTimeout/sleep in tests",
    "R6.4": "Hermetic test state isolation: isolate DB/state paths per test in setUp/addCleanup",
    "R6.5": "Post-incident regression crystallization: every bug fix includes a failing-first test",
    # R7: Architecture & Contracts (5 rules)
    "R7.1": "Contract-first monorepo changes: update shared Zod/OpenAPI schema before consumers",
    "R7.2": "Granular field validation: return field-level errors and preserve user form inputs",
    "R7.3": "Single canonical route per path: no duplicate route group paths",
    "R7.4": "Acyclic module layering: domain -> application -> adapters; no circular imports",
    "R7.5": "Universal contracts purity: contracts barrels must not import Node built-ins (node:fs, node:path)",
    # R8: Marketing & Attribution (3 rules)
    "R8.1": "Anti-cloaking & markdown parity: serve identical facts to crawlers and browsers",
    "R8.2": "Honest telemetry attribution: label synthetic/demo data; never mix with live metrics",
    "R8.3": "Consent Mode v2 ordering: initialize default denied consent before analytics tags",
    # R9: TypeScript / Type Safety (3 rules)
    "R9.1": "No untyped escape hatches: no `as any` casts or `z.any()` schemas in production source",
    "R9.2": "No silenced type errors: no @ts-ignore; every @ts-expect-error states its reason",
    "R9.3": "Package-name imports: import workspace packages by name, never via ../../packages/ paths",
    # R10: API & Network Robustness (8 rules)
    "R10.1": "Explicit HTTP request timeouts: every fetch/axios call specifies timeout or AbortSignal",
    "R10.2": "Idempotency key transmission: mutating external POST/PUT requests send Idempotency-Key",
    "R10.3": "Rate-limit header handling: parse 429 Retry-After and respect backoff deadlines",
    "R10.4": "Structured error envelope: error responses adhere to standard JSON error schema",
    "R10.5": "Response size bounding: clamp response body reads to avoid unbounded buffer allocation",
    "R10.6": "Content-Type negotiation: validate incoming request Accept / Content-Type headers",
    "R10.7": "No unauthenticated admin endpoints: route middleware protects management routes",
    "R10.8": "Strict HTTP verb mapping: GET requests must be strictly read-only and side-effect free",
    # R11: State Management & Concurrency (8 rules)
    "R11.1": "Atomic read-modify-write: concurrent mutations use compare-and-swap or row locks",
    "R11.2": "No dangling unawaited promises: promise chains either return or await explicitly",
    "R11.3": "Race condition prevention: UI mutations abort pending conflicting requests via AbortController",
    "R11.4": "Deterministic reducer purity: state reducers remain pure functions without side effects",
    "R11.5": "Cache key stability: cache keys use sorted/normalized parameters to avoid fragmentation",
    "R11.6": "Optimistic UI rollback: optimistic state updates retain rollback snapshot on failure",
    "R11.7": "Bounded in-memory queues: memory queues specify max length and overflow policy",
    "R11.8": "Thread-safe singleton initialization: singletons use atomic locks or double-checked init",
    # R12: Memory & Resource Leak Prevention (8 rules)
    "R12.1": "Event listener teardown: addEventListener in useEffect/components pairs with removeEventListener",
    "R12.2": "Timer lifecycle cleanup: setTimeout and setInterval handle IDs cleaned on component unmount",
    "R12.3": "Stream disposal hygiene: open readable/writable streams explicitly call close() or pipe safely",
    "R12.4": "WebSocket cleanup: client socket connections explicitly disconnect on navigation/unmount",
    "R12.5": "Database connection pool hygiene: acquired pool clients release in finally blocks",
    "R12.6": "Worker thread termination: spawn worker instances call terminate() upon task completion",
    "R12.7": "Temp file deterministic deletion: scratch files in /tmp register unlink in finalizer",
    "R12.8": "No unbounded collection growth: caches and registries specify TTL or LRU eviction",
    # R13: Observability & Logging Hygiene (8 rules)
    "R13.1": "Zero secret logging: redact passwords, tokens, API keys, and authorization headers",
    "R13.2": "Structured JSON logging: application logs emit valid JSON key-value pairs with timestamps",
    "R13.3": "Trace context propagation: distributed calls forward traceparent / correlation IDs",
    "R13.4": "Metric label cardinality bounding: avoid dynamic user IDs or timestamps in metric labels",
    "R13.5": "Standard log severity: use debug/info/warn/error appropriately without log spam",
    "R13.6": "Audit event journaling: security-critical actions append an immutable audit record",
    "R13.7": "Health check hermeticity: /healthz endpoints execute lightweight non-allocating probes",
    "R13.8": "Exception traceback containment: sanitize public error responses to avoid leaking paths",
    # R14: Auth & Session Hardening (8 rules)
    "R14.1": "Session token entropy: session identifiers contain at least 128 bits of cryptosecure random",
    "R14.2": "Password hash modern algorithms: use Argon2id or bcrypt with appropriate work factor",
    "R14.3": "Token expiration bounding: short-lived access tokens paired with rotating refresh tokens",
    "R14.4": "CSRF token validation: state-changing forms and endpoints validate anti-CSRF token",
    "R14.5": "No credentials in URLs: tokens, API keys, and passwords never passed in query strings",
    "R14.6": "Strict redirect URL allowlist: OAuth / login return URLs validated against domain allowlist",
    "R14.7": "Brute-force throttle: login and reset-password routes rate-limited by IP and username",
    "R14.8": "Role-based access control: enforce authorization check at controller/handler boundary",
    # R15: Error Boundaries & Fallback Rendering (8 rules)
    "R15.1": "React error boundary protection: major route segments wrapped in error boundaries",
    "R15.2": "Non-blocking third-party failures: external widgets render graceful placeholder on failure",
    "R15.3": "Form submit recovery: failed form submission preserves user input for retry",
    "R15.4": "Image broken state fallback: img / Image tags provide alt and error state fallback",
    "R15.5": "Network offline banner: offline connectivity state indicated with non-blocking alert",
    "R15.6": "Empty state affordance: data tables and lists display actionable empty state message",
    "R15.7": "Skeleton loader transition: loading states use layout-preserving skeletons to avoid CLS",
    "R15.8": "Recoverable 404 navigation: not-found pages provide search and home navigation links",
    # R16: Supply Chain & Dependency Hygiene (8 rules)
    "R16.1": "Lockfile integrity enforcement: CI installs strictly via frozen lockfiles (pnpm --frozen)",
    "R16.2": "No wildcard dependency versions: package.json avoids '*' or unbounded range dependencies",
    "R16.3": "Scoped internal packages: monorepo internal packages use scoped organization prefixes",
    "R16.4": "No install script execution: untrusted packages ignore postinstall lifecycle scripts",
    "R16.5": "Production bundle minimization: devDependencies not imported in production runtime code",
    "R16.6": "License compliance: no copyleft (GPL) dependencies imported into proprietary modules",
    "R16.7": "Single package manager: repo roots maintain exactly one package manager lockfile",
    "R16.8": "Deterministic engine constraints: package.json specifies minimum node/pnpm engines",
    # R17: Modern React & Next.js Patterns (8 rules)
    "R17.1": "Server Component default: components in app directory default to RSC unless 'use client'",
    "R17.2": "No server-only code in client: 'server-only' imports barred from client-marked components",
    "R17.3": "Metadata API compliance: route pages export static or generateMetadata for SEO",
    "R17.4": "Next/Image usage: production UI renders next/image for optimized srcset and layout stability",
    "R17.5": "Next/Font optimization: load Google/local fonts via next/font with zero layout shift",
    "R17.6": "Client boundary minimization: push 'use client' directives down to leaf interactive nodes",
    "R17.7": "Server action security: server actions validate session authentication before mutating",
    "R17.8": "Route handler return typing: route handlers return typed NextResponse with status",
    # R18: Accessibility (WCAG 2.1 AA) (8 rules)
    "R18.1": "Meaningful image alternative text: informative images supply descriptive alt attribute",
    "R18.2": "Form control labels: every input, select, and textarea element has associated label",
    "R18.3": "Keyboard navigation accessibility: interactive elements focusable via Tab and Enter/Space",
    "R18.4": "Contrast ratio minimum: text satisfies 4.5:1 minimum contrast ratio against background",
    "R18.5": "No click handlers on non-interactive elements: divs/spans with onClick specify role='button'",
    "R18.6": "Aria attributes validity: aria-* attributes use valid names and permissible state values",
    "R18.7": "Visible focus rings: interactive elements retain visible focus outline for keyboard users",
    "R18.8": "Document language attribute: html root element specifies valid lang='en' attribute",
    # R19: Clean Code & Maintainability Guardrails (4 rules)
    "R19.1": "Function length limit: functions remain under 100 lines; extract complex branches",
    "R19.2": "Cyclomatic complexity bounding: functions maintain cyclomatic complexity <= 20",
    "R19.3": "No dead commented-out code: remove obsolete commented code blocks prior to PR merge",
    "R19.4": "Descriptive variable naming: avoid single-character variables outside trivial loops",
}


# Pre-compiled regex patterns for common rule violations on added lines
_SECRET_RX = re.compile(
    r"""(?i)(?:api[_-]?key|secret|password|bearer|auth[_-]?token)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]"""
)
_DANGEROUS_HTML_RX = re.compile(r"dangerouslySetInnerHTML\s*=\s*\{\s*\{\s*__html\b")
_EVAL_RX = re.compile(r"\b(?:eval|Function)\s*\(")
_NO_ALT_IMG_RX = re.compile(r"<img\b(?!.*?alt=)[^>]*>", re.I)
_CLICK_ON_DIV_RX = re.compile(r"<div\b[^>]*onClick\s*=(?!.*?role=)[^>]*>", re.I)
_UNBOUNDED_QUERY_RX = re.compile(r"\.(?:findMany|select)\s*\(\s*\{(?![^}]*take\s*:)(?![^}]*limit\s*:)", re.I)
_AS_ANY_RX = re.compile(r"\bas\s+any(?![\w$])|\bz\.any\s*\(")
_TS_IGNORE_RX = re.compile(r"@ts-ignore\b")
_EMPTY_CATCH_RX = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")
_BARE_EXCEPT_RX = re.compile(r"^\s*\+?\s*except\s*:")
_WAIT_FOR_TIMEOUT_RX = re.compile(r"\bwaitForTimeout\s*\(\s*\d+")


def _check_line_patterns(rel_path: str, lno: int, line: str, findings: list[str]) -> None:
    """Helper to evaluate single-line AST and regex rules."""
    ext = os.path.splitext(rel_path)[1].lower()
    is_script = ext in (".ts", ".tsx", ".js", ".jsx")
    is_ui = ext in (".tsx", ".jsx")

    if _SECRET_RX.search(line) and not ("example" in line.lower() or "test" in line.lower()):
        findings.append(f"{rel_path}:{lno}: [R13.1] Hardcoded secret pattern detected in added code")

    if ext == ".py":
        if _BARE_EXCEPT_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R5.4] Bare `except:` detected; specify explicit exception tuple")

    if is_script:
        if _AS_ANY_RX.search(line) and "test" not in rel_path.lower():
            findings.append(f"{rel_path}:{lno}: [R9.1] Untyped escape hatch `as any` or `z.any()` in production source")
        if _TS_IGNORE_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R9.2] `@ts-ignore` used; use `@ts-expect-error` with explanatory reason")
        if _EMPTY_CATCH_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R5.4] Empty catch block detected; handle or log the error")
        if _EVAL_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R2.5] Unsafe `eval` or dynamic `Function` constructor detected")

    if is_ui:
        if _DANGEROUS_HTML_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R2.5] Unsanitized `dangerouslySetInnerHTML` in UI component")
        if _NO_ALT_IMG_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R18.1] Missing `alt` attribute on `<img>` element")
        if _CLICK_ON_DIV_RX.search(line):
            findings.append(f"{rel_path}:{lno}: [R18.5] `onClick` handler on non-interactive `<div>` without `role`")

    if "test" in rel_path.lower() and _WAIT_FOR_TIMEOUT_RX.search(line):
        findings.append(f"{rel_path}:{lno}: [R6.3] `waitForTimeout` sleep in test; use deterministic assertions")


def scan_added_lines_for_rules(
    added_lines_by_file: dict[str, list[str]],
) -> list[str]:
    """Scan added lines across changed files against portable zero-token code rules."""
    findings: list[str] = []
    for rel_path, lines in added_lines_by_file.items():
        for lno, line in enumerate(lines, 1):
            _check_line_patterns(rel_path, lno, line, findings)
    return findings


def scan_lines(rel_path: str, numbered: list[tuple[int, str]]) -> list[str]:
    """Scan ``(line_no, text)`` pairs of one file, keeping the real line numbers (a diff's added lines)."""
    findings: list[str] = []
    for lno, line in numbered:
        _check_line_patterns(rel_path, lno, line, findings)
    return findings
