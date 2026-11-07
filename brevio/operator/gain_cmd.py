"""The savings receipt: `cli.py gain` in the harness, `brevio-core gain` in the package."""
from __future__ import annotations

import argparse
import json
import sys

from brevio.pipeline import core_cli
from brevio.pipeline.gates import dopamine_ledger


def main(argv: list[str] | None = None, prog: str = "cli.py gain") -> int:
    """Print the savings receipt; ``prog`` is how the user types the command."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Show the savings receipt: defects intercepted, learned guards active, and savings when measured.",
    )
    parser.add_argument("--json", action="store_true", help="Output metrics as JSON")
    if core_cli.up_tools() is not None:     # the 0.6 set: the closing Teams line (ROADMAP E37, 2026-11-05)
        parser.add_argument("--no-upgrade-line", action="store_true", help="leave out the closing Teams line")

    args = parser.parse_args(argv)
    summary = dopamine_ledger.get_gain_summary()

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    interceptions = summary["total_interceptions"]
    guards = summary["active_learned_guards"]
    receipt = summary["receipt_url"]

    print("═══════════════════════════════════════════════════════════════")
    print("  brevio-core gain — Savings Receipt (G13)")
    print("═══════════════════════════════════════════════════════════════")
    print(f"  {interceptions:,} defects intercepted, {guards:,} learned guards active")
    print(f"  Base Rules Enforced:     {summary['base_rules_enforced']} PR rules (code_rules)")
    if summary["savings_measured"]:
        print(f"  Tokens saved (measured): {summary['tokens_saved']:,}")
        print(f"  Spend saved (measured):  ${summary['cost_saved_usd']:,.2f} USD")
    print(f"  AEO Readiness Score:     {summary.get('aeo_score', 100)}/100")
    print("───────────────────────────────────────────────────────────────")
    print("  Shareable Verified Receipt:")
    print(f"  {receipt}")
    print(f"  Markdown Badge: [![Verified by brevio-core]({receipt})](https://brevio.pro/tools/rules-encyclopedia)")
    print("═══════════════════════════════════════════════════════════════")
    teams = core_cli.upgrade_line("gain", not getattr(args, "no_upgrade_line", False))
    if teams:
        print(teams)
    return 0


if __name__ == "__main__":
    sys.exit(main())
