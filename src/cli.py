#!/usr/bin/env python3
"""
AgentAI Agency — Command Line Interface

Usage examples:
  python3 src/cli.py initiate --from sales --to account --inputs lead_profile deal_status target_kpi
  python3 src/cli.py approve --id <uuid>
  python3 src/cli.py block  --id <uuid> --reason "Client unresponsive"
  python3 src/cli.py list
  python3 src/cli.py list --state draft
  python3 src/cli.py status
  python3 src/cli.py refresh-overdue
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from project root: python3 src/cli.py
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import store
from engine import WorkflowEngine
from models import HandoffState


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

STATE_COLORS = {
    "draft":    "\033[94m",   # blue
    "approved": "\033[92m",   # green
    "blocked":  "\033[91m",   # red
    "overdue":  "\033[93m",   # yellow
}
RESET = "\033[0m"


def _colored_state(state: str) -> str:
    return f"{STATE_COLORS.get(state, '')}{state.upper()}{RESET}"


def _print_handoff(h) -> None:
    d = store.handoff_to_dict(h)
    route = f"{d['policy']['from_department']} → {d['policy']['to_department']}"
    print(f"  ID      : {d['id']}")
    print(f"  Route   : {route}")
    print(f"  State   : {_colored_state(d['state'])}")
    print(f"  SLA     : {d['policy']['sla_hours']}h  |  Approver: {d['policy']['approver_role']}")
    print(f"  Inputs  : {', '.join(d['provided_inputs'])}")
    print(f"  Created : {d['created_at'][:19]}")
    print(f"  Updated : {d['updated_at'][:19]}")
    if d["notes"]:
        print(f"  Notes   : {d['notes']}")
    print()


def _make_engine() -> WorkflowEngine:
    engine = WorkflowEngine()
    engine.restore(store.load())
    return engine


# ------------------------------------------------------------------ #
# Sub-command handlers                                                 #
# ------------------------------------------------------------------ #

def cmd_initiate(args) -> None:
    engine = _make_engine()
    try:
        h = engine.initiate(args.from_dept, args.to_dept, tuple(args.inputs))
        store.save(engine.export_handoffs())
        print(f"\n✓ Handoff created [{_colored_state(h.state.value)}]\n")
        _print_handoff(h)
    except (KeyError, ValueError) as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        sys.exit(1)


def cmd_approve(args) -> None:
    engine = _make_engine()
    try:
        h = engine.approve(args.id)
        store.save(engine.export_handoffs())
        print(f"\n✓ Handoff approved [{_colored_state(h.state.value)}]\n")
        _print_handoff(h)
    except (KeyError, ValueError) as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        sys.exit(1)


def cmd_block(args) -> None:
    engine = _make_engine()
    try:
        h = engine.block(args.id, reason=args.reason or "")
        store.save(engine.export_handoffs())
        print(f"\n✓ Handoff blocked [{_colored_state(h.state.value)}]\n")
        _print_handoff(h)
    except (KeyError, ValueError) as e:
        print(f"\n✗ {e}\n", file=sys.stderr)
        sys.exit(1)


def cmd_list(args) -> None:
    engine = _make_engine()
    if args.state:
        try:
            state = HandoffState(args.state)
        except ValueError:
            valid = ", ".join(s.value for s in HandoffState)
            print(f"\n✗ Invalid state '{args.state}'. Valid: {valid}\n", file=sys.stderr)
            sys.exit(1)
        items = engine.get_by_state(state)
    else:
        items = engine.all_handoffs()

    if not items:
        print("\n  (no handoffs found)\n")
        return

    print(f"\n{'─'*60}")
    for h in sorted(items, key=lambda x: x.created_at):
        _print_handoff(h)


def cmd_status(args) -> None:
    engine = _make_engine()
    counts = engine.status()
    total = sum(counts.values())
    print(f"\n{'─'*40}")
    print(f"  Agency Handoff Dashboard  (total: {total})")
    print(f"{'─'*40}")
    for state, count in counts.items():
        bar = "█" * count + "░" * max(0, 10 - count)
        print(f"  {_colored_state(state):<30} {bar}  {count}")
    print(f"{'─'*40}\n")


def cmd_refresh_overdue(args) -> None:
    engine = _make_engine()
    flagged = engine.refresh_overdue()
    store.save(engine.export_handoffs())
    if not flagged:
        print("\n  No handoffs past SLA deadline.\n")
    else:
        print(f"\n  {len(flagged)} handoff(s) marked OVERDUE:\n")
        for h in flagged:
            _print_handoff(h)


# ------------------------------------------------------------------ #
# Argument parser                                                      #
# ------------------------------------------------------------------ #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agency",
        description="AgentAI Agency — Workflow CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # initiate
    p = sub.add_parser("initiate", help="Create a new handoff between two departments")
    p.add_argument("--from", dest="from_dept", required=True, metavar="DEPT",
                   help="Source department (e.g. sales)")
    p.add_argument("--to", dest="to_dept", required=True, metavar="DEPT",
                   help="Target department (e.g. account)")
    p.add_argument("--inputs", nargs="+", required=True, metavar="INPUT",
                   help="Space-separated input keys (e.g. lead_profile deal_status)")
    p.set_defaults(func=cmd_initiate)

    # approve
    p = sub.add_parser("approve", help="Approve a pending handoff")
    p.add_argument("--id", required=True, metavar="UUID", help="Handoff ID")
    p.set_defaults(func=cmd_approve)

    # block
    p = sub.add_parser("block", help="Block a handoff with an optional reason")
    p.add_argument("--id", required=True, metavar="UUID", help="Handoff ID")
    p.add_argument("--reason", default="", metavar="TEXT", help="Reason for blocking")
    p.set_defaults(func=cmd_block)

    # list
    p = sub.add_parser("list", help="List handoffs (optionally filter by state)")
    p.add_argument("--state", choices=[s.value for s in HandoffState],
                   metavar="STATE", help="Filter: draft|approved|blocked|overdue")
    p.set_defaults(func=cmd_list)

    # status
    p = sub.add_parser("status", help="Show dashboard summary by state")
    p.set_defaults(func=cmd_status)

    # refresh-overdue
    p = sub.add_parser("refresh-overdue", help="Scan for handoffs past their SLA and mark overdue")
    p.set_defaults(func=cmd_refresh_overdue)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
