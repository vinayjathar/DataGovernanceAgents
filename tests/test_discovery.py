import csv
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from governance.agents.discovery import DiscoveryAgent, infer_column_type  # noqa: E402
from governance.catalog import Catalog  # noqa: E402
from governance.events import EventBus  # noqa: E402


class InferColumnTypeTests(unittest.TestCase):
    def test_integer_column(self):
        self.assertEqual(infer_column_type(["1", "2", "3"]), "integer")

    def test_float_column(self):
        self.assertEqual(infer_column_type(["1.5", "2.25"]), "float")

    def test_date_column(self):
        self.assertEqual(infer_column_type(["2023-01-01", "2023-02-15"]), "date")

    def test_string_column(self):
        self.assertEqual(infer_column_type(["Ravi Shah", "Wei Chen"]), "string")

    def test_ignores_blanks_when_voting(self):
        self.assertEqual(infer_column_type(["1", "", "2"]), "integer")

    def test_empty_column_defaults_to_string(self):
        self.assertEqual(infer_column_type(["", ""]), "string")


class DiscoveryAgentScanTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmpdir.name)
        with (self.data_dir / "widgets.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["widget_id", "name", "price", "notes"])
            writer.writerow(["1", "Bolt", "0.50", ""])
            writer.writerow(["2", "Nut", "0.25", "backordered"])

        self.catalog = Catalog()
        self.agent = DiscoveryAgent(EventBus(), self.catalog)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_registers_dataset_with_inferred_schema(self):
        entries = self.agent.scan(self.data_dir)
        self.assertEqual(len(entries), 1)

        entry = self.catalog.datasets["widgets"]
        self.assertEqual(entry.row_count, 2)

        by_name = {c.name: c for c in entry.columns}
        self.assertEqual(by_name["widget_id"].inferred_type, "integer")
        self.assertEqual(by_name["price"].inferred_type, "float")
        self.assertEqual(by_name["notes"].null_count, 1)

    def test_publishes_dataset_discovered_event(self):
        seen = []
        self.agent.bus.subscribe("dataset.discovered", lambda payload: seen.append(payload))
        self.agent.scan(self.data_dir)
        self.assertEqual(seen, [{"dataset": "widgets"}])


if __name__ == "__main__":
    unittest.main()
