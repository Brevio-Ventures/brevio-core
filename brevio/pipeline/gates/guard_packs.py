"""Progressive-Disclosure Community Guard Packs (Master Growth Plan G14 / S7).

Curated zero-token AST guard packs installable via `brevio-core add <pack>`:
- nextjs-app-router
- stripe-polar-billing
- fastapi-async
- eu-ai-act
- supabase-rls
"""
from __future__ import annotations

import os
from typing import Any

from brevio.pipeline.agent_host import config
from brevio.pipeline.gates import defect_compiler

PACKS: dict[str, dict[str, Any]] = {
    "nextjs-app-router": {
        "name": "nextjs-app-router",
        "description": "Next.js App Router hydration, client/server boundaries, and metadata rules",
        "guards": [
            {
                "id": "pack-nextjs-no-async-client",
                "title": "Client components must not be async functions",
                "category": "robustness",
                "file_patterns": ["**/*.tsx", "**/*.jsx"],
                "patterns": ["async function.*use client", "re:['\"]use client['\"][\\s\\S]*?async\\s+function"],
            },
            {
                "id": "pack-nextjs-metadata-server-only",
                "title": "Metadata exports are only valid in server components",
                "category": "robustness",
                "file_patterns": ["**/*.tsx", "**/*.jsx"],
                "patterns": ["re:['\"]use client['\"][\\s\\S]*?export\\s+const\\s+metadata"],
            },
        ],
    },
    "stripe-polar-billing": {
        "name": "stripe-polar-billing",
        "description": "Stripe & Polar billing webhook signature verification & idempotency guards",
        "guards": [
            {
                "id": "pack-billing-webhook-raw-body",
                "title": "Billing webhooks must verify signature using raw unparsed body",
                "category": "security",
                "file_patterns": ["**/webhook*.*", "**/api/billing/**", "**/api/stripe/**"],
                "patterns": ["JSON.parse.*constructEvent", "req.body.*constructEvent"],
            },
            {
                "id": "pack-billing-idempotency-key",
                "title": "Payment mutations must pass an idempotency key",
                "category": "finops",
                "file_patterns": ["**/billing/**", "**/payments/**"],
                "patterns": ["re:stripe\\.(?:charges|paymentIntents)\\.create\\(\\s*\\{[^}]*(?!idempotencyKey)[^}]*\\}\\)"],
            },
        ],
    },
    "fastapi-async": {
        "name": "fastapi-async",
        "description": "FastAPI async event-loop safety & lifespan context guards",
        "guards": [
            {
                "id": "pack-fastapi-no-blocking-io",
                "title": "Async route handlers must not invoke blocking sleep or sync I/O",
                "category": "robustness",
                "file_patterns": ["**/*.py"],
                "patterns": ["re:requests\\.(get|post|put|delete)\\(|time\\.sleep\\("],
            },
            {
                "id": "pack-fastapi-lifespan",
                "title": "Use lifespan context manager instead of deprecated on_event",
                "category": "robustness",
                "file_patterns": ["**/*.py"],
                "patterns": ['@app.on_event("startup")', "@app.on_event('startup')"],
            },
        ],
    },
    "eu-ai-act": {
        "name": "eu-ai-act",
        "description": "EU AI Act statutory transparency headers and consent logging",
        "guards": [
            {
                "id": "pack-ai-transparency-header",
                "title": "AI inference endpoints must return X-AI-Generated transparency header",
                "category": "compliance",
                "file_patterns": ["**/api/chat/**", "**/api/generate/**", "**/api/llm/**"],
                "patterns": ["re:return\\s+(?:NextResponse|Response)\\.json\\((?!.*X-AI-Generated)"],
            },
        ],
    },
    "supabase-rls": {
        "name": "supabase-rls",
        "description": "Supabase client security & Row Level Security (RLS) enforcement",
        "guards": [
            {
                "id": "pack-supabase-no-service-key-client",
                "title": "Browser client bundles must never import SUPABASE_SERVICE_ROLE_KEY",
                "category": "security",
                "file_patterns": ["apps/web/**", "src/client/**", "src/components/**"],
                "patterns": ["process.env.SUPABASE_SERVICE_ROLE_KEY", "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY"],
            },
        ],
    },
}


def list_packs() -> list[dict[str, Any]]:
    return [
        {"id": k, "name": p["name"], "description": p["description"], "guard_count": len(p["guards"])}
        for k, p in PACKS.items()
    ]


def install_pack(pack_name: str, cwd: str | None = None) -> list[str]:
    """Install a curated community guard pack into .brevio/guards.json and .agents/rules/."""
    pack = PACKS.get(pack_name)
    if not pack:
        raise KeyError(f"Unknown community guard pack: '{pack_name}'. Available: {list(PACKS.keys())}")

    workspace = cwd or config.WORKSPACE_DIR
    installed_ids = []

    data = defect_compiler.load_guards(workspace)
    guards = data.setdefault("guards", {})

    for g_spec in pack["guards"]:
        gid = g_spec["id"]
        title = g_spec["title"]
        category = g_spec["category"]
        file_patterns = g_spec["file_patterns"]
        patterns = g_spec["patterns"]

        rule_path = defect_compiler._write_agent_rule(
            guard_id=gid,
            title=title,
            category=category,
            file_globs=file_patterns,
            patterns=patterns,
            cwd=workspace,
        )

        record = {
            "id": gid,
            "title": title,
            "category": category,
            "pack": pack_name,
            "file_patterns": file_patterns,
            "patterns": patterns,
            "status": "active",
            "runs_evaluated": 0,
            "false_fails": 0,
            "intercepted": 0,
            "rule_file": os.path.relpath(rule_path, workspace),
            "created_at": defect_compiler._now_iso(),
            "updated_at": defect_compiler._now_iso(),
        }
        guards[gid] = record
        installed_ids.append(gid)

    defect_compiler.save_guards(data, workspace)
    return installed_ids
