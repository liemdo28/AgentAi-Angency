from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from engine import WorkflowEngine
from models import HandoffState
from policies import POLICIES


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WorkflowEngine(POLICIES)

    def test_initiate_success(self) -> None:
        handoff = self.engine.initiate_handoff(
            "sales",
            "account",
            {"lead_profile": "a", "deal_status": "won", "target_kpi": "roas"},
        )
        self.assertEqual(HandoffState.DRAFT, handoff.state)

    def test_missing_input_fails(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.initiate_handoff("sales", "account", {"lead_profile": "a"})

    def test_unknown_route_fails(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.initiate_handoff("sales", "unknown", {})

    def test_approve_block_and_status(self) -> None:
        handoff = self.engine.initiate_handoff(
            "sales",
            "account",
            {"lead_profile": "a", "deal_status": "won", "target_kpi": "roas"},
        )
        self.engine.approve(handoff.id, "ok")
        self.assertEqual(HandoffState.APPROVED, self.engine.get_handoff(handoff.id).state)

        handoff2 = self.engine.initiate_handoff(
            "account",
            "strategy",
            {"project_brief": "b", "client_constraints": "c", "budget": "100"},
        )
        self.engine.block(handoff2.id, "missing data")
        self.assertEqual(HandoffState.BLOCKED, self.engine.get_handoff(handoff2.id).state)

        status = self.engine.status_dashboard()
        self.assertEqual(2, status["total"])


if __name__ == "__main__":
    unittest.main()
