import unittest
from datetime import date

from helpers import CONFIG, full_run

from governance.agents.retention import RetentionAgent
from governance.catalog import Catalog
from governance.events import EventBus


class RetentionAgentTests(unittest.TestCase):
    """as_of is passed explicitly everywhere so these never drift with the clock."""

    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run(as_of=date(2026, 8, 22))
        cls.findings = {f.dataset: f for f in cls.catalog.retention_findings}

    def test_order_records_past_their_three_year_schedule_are_due(self):
        finding = self.findings["orders"]
        self.assertEqual(finding.status, "due_for_disposition")
        self.assertEqual(finding.retain_until, "2026-04-05")

    def test_customer_records_inside_their_seven_year_schedule_are_retained(self):
        self.assertEqual(self.findings["customers"].status, "within_schedule")

    def test_unowned_dataset_falls_back_to_the_default_schedule(self):
        finding = self.findings["legacy_customers"]
        self.assertEqual(finding.retention_class, "unclassified")
        self.assertEqual(finding.status, "due_for_disposition")

    def test_dataset_with_no_date_column_is_skipped(self):
        self.assertNotIn("products", self.findings)

    def test_due_findings_raise_an_issue(self):
        due = [f for f in self.catalog.retention_findings if f.status == "due_for_disposition"]
        retention_issues = [i for i in self.catalog.issues if i.raised_by == "AG-10"]
        self.assertEqual(len(due), len(retention_issues))

    def test_legal_hold_blocks_disposition_even_when_the_schedule_expired(self):
        catalog = Catalog()
        _, source_catalog, _ = full_run(as_of=date(2026, 8, 22))
        catalog.datasets = source_catalog.datasets

        agent = RetentionAgent(
            EventBus(),
            catalog,
            schedules={"order_records": {"retention_years": 3, "basis": "test"}},
            legal_holds=["orders"],
        )
        findings = {f.dataset: f for f in agent.evaluate(as_of=date(2026, 8, 22))}
        self.assertEqual(findings["orders"].status, "legal_hold")

    def test_schedule_boundary_is_inclusive(self):
        """A dataset whose retention date is exactly today is due, not retained."""
        _, source_catalog, _ = full_run(as_of=date(2026, 8, 22))
        catalog = Catalog()
        catalog.datasets = source_catalog.datasets

        agent = RetentionAgent(
            EventBus(),
            catalog,
            schedules={"order_records": {"retention_years": 3, "basis": "test"}},
        )
        findings = {f.dataset: f for f in agent.evaluate(as_of=date(2026, 4, 5))}
        self.assertEqual(findings["orders"].status, "due_for_disposition")


if __name__ == "__main__":
    unittest.main()
