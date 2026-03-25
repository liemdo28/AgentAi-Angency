from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ai.orchestrator import AutonomousAgency
from ai.models import TaskStatus


class AutonomousAgencyTests(unittest.TestCase):
    def test_create_and_run_task(self) -> None:
        agency = AutonomousAgency()
        task = agency.create_task(
            goal="Generate launch campaign",
            kpi="CTR > 2%",
            deadline="2026-03-30",
            department="creative",
            context={"brief": "restaurant campaign", "brand": "bakudan"},
        )
        updated = agency.run_task(task.id)
        self.assertIn(updated.status, {TaskStatus.COMPLETED, TaskStatus.FAILED})
        self.assertGreater(updated.score, 0)

    def test_unknown_department_fails(self) -> None:
        agency = AutonomousAgency()
        with self.assertRaises(ValueError):
            agency.create_task(
                goal="test",
                kpi="test",
                deadline="2026-03-30",
                department="unknown",
            )


if __name__ == "__main__":
    unittest.main()
