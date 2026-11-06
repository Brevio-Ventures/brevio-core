"""Community guard packs: `cli.py pack` in the harness, `brevio-core add` in the package."""
from __future__ import annotations

import argparse
import json
import sys

from brevio.pipeline.gates import guard_packs


def main(argv: list[str] | None = None, prog: str = "cli.py pack") -> int:
    """List or add guard packs; ``prog`` is how the user types the command (``brevio-core`` for ``add``)."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Install curated zero-token community guard packs (Next.js, Stripe, FastAPI, EU AI Act, Supabase).",
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    subparsers = parser.add_subparsers(dest="subcommand")
    list_p = subparsers.add_parser("list", help="List available community guard packs")
    list_p.add_argument("--json", action="store_true", help="Output result as JSON")
    add_p = subparsers.add_parser("add", help="Add a community guard pack")
    add_p.add_argument("pack", help="Name of the pack to install")
    add_p.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args(argv)
    cmd = args.subcommand or "list"

    if cmd == "list":
        packs = guard_packs.list_packs()
        if args.json:
            print(json.dumps(packs, indent=2))
            return 0
        print("═══════════════════════════════════════════════════════════════")
        print("  brevio-core packs — Community Zero-Token Guard Packs (G14)")
        print("═══════════════════════════════════════════════════════════════")
        for p in packs:
            print(f"  • {p['name']:<24} ({p['guard_count']} guards)")
            print(f"    {p['description']}")
        print(f"\nInstall any pack with `{prog} add <name>` (adds 0 prompt tokens).")
        return 0

    if cmd == "add":
        try:
            installed = guard_packs.install_pack(args.pack)
            if args.json:
                print(json.dumps({"pack": args.pack, "installed_guards": installed, "status": "ok"}))
                return 0
            print(f"✅ Successfully installed pack '{args.pack}' ({len(installed)} guards active):")
            for gid in installed:
                print(f"  • {gid}")
            print("Guards active in `.brevio/guards.json` and `.agents/rules/` at 0 base tokens.")
            return 0
        except KeyError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
