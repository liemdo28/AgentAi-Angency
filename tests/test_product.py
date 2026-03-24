from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from product import ProductManager


class ProductTests(unittest.TestCase):
    def test_create_client_and_project(self) -> None:
        manager = ProductManager()
        client = manager.create_client("Bakudan", "Restaurant")
        project = manager.create_project(client.id, "Launch Q2", "Scale revenue", "AM")

        self.assertEqual(client.id, project.client_id)
        self.assertEqual(1, len(manager.list_clients()))
        self.assertEqual(1, len(manager.list_projects()))

    def test_project_requires_existing_client(self) -> None:
        manager = ProductManager()
        with self.assertRaises(ValueError):
            manager.create_project("missing", "Launch", "Scale", "AM")


if __name__ == "__main__":
    unittest.main()
