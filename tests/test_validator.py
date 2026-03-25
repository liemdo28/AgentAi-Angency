import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agency_registry import load_all_departments
from policies.validator import validate_policies


class ValidatorTests(unittest.TestCase):
    def test_registry_loads_all_departments(self) -> None:
        departments = load_all_departments()
        self.assertEqual(11, len(departments))
        self.assertIn("crm_automation", departments)

    def test_policy_validation_has_no_errors(self) -> None:
        errors = validate_policies()
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
