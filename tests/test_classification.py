import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from governance.agents.classification import detect_kinds  # noqa: E402
from governance.agents.orchestrator import Orchestrator  # noqa: E402
from governance.catalog import Catalog  # noqa: E402

MOCK_DATA = REPO_ROOT / "mock_data"


class DetectKindsTests(unittest.TestCase):
    def test_detects_email_in_values(self):
        kinds = detect_kinds("notes", ["call me at ravi.shah@example.com please"])
        self.assertIn("email", kinds)

    def test_detects_ssn_in_values(self):
        kinds = detect_kinds("notes", ["ssn on file 521-11-4487"])
        self.assertIn("ssn", kinds)

    def test_does_not_confuse_phone_with_ssn(self):
        kinds = detect_kinds("phone", ["415-555-0199"])
        self.assertEqual(kinds, {"phone"})

    def test_name_hint_fires_even_with_no_sample_values(self):
        kinds = detect_kinds("ssn", [])
        self.assertEqual(kinds, {"ssn"})

    def test_clean_column_has_no_kinds(self):
        kinds = detect_kinds("category", ["Electronics", "Furniture"])
        self.assertEqual(kinds, set())


class OrchestratorPhase0IntegrationTests(unittest.TestCase):
    """Runs the full AG-02 -> AG-03 -> AG-11 chain over the real mock dataset."""

    def setUp(self):
        self.catalog = Catalog()
        self.orchestrator = Orchestrator(self.catalog)
        self.orchestrator.run_phase0(MOCK_DATA)

    def test_approved_pii_is_labeled_without_an_issue(self):
        customers = self.catalog.datasets["customers"]
        email_col = next(c for c in customers.columns if c.name == "email")
        self.assertEqual(email_col.sensitivity, "restricted")
        self.assertIn("email", email_col.regulatory_tags)

    def test_pii_outside_approved_zone_raises_exactly_one_issue(self):
        issues = self.catalog.open_issues()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].dataset, "orders")
        self.assertEqual(issues[0].column, "notes")
        self.assertEqual(set(self.catalog.datasets["orders"].columns[-1].regulatory_tags), {"email", "ssn"})

    def test_columns_with_no_pii_are_labeled_general(self):
        products = self.catalog.datasets["products"]
        name_col = next(c for c in products.columns if c.name == "product_name")
        self.assertEqual(name_col.sensitivity, "general")


if __name__ == "__main__":
    unittest.main()
