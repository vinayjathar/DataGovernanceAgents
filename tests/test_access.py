import unittest

from helpers import full_run


class AccessAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run()
        cls.decisions = {d.request_id: d for d in cls.catalog.access_decisions}

    def test_dataset_with_no_restricted_columns_is_auto_approved(self):
        decision = self.decisions["REQ-001"]
        self.assertEqual(decision.decision, "auto-approved")
        self.assertEqual(decision.risk, "low")
        self.assertEqual(decision.decided_by, "AG-08 (auto)")

    def test_special_category_data_escalates_to_the_owner(self):
        decision = self.decisions["REQ-002"]
        self.assertEqual(decision.decision, "escalated")
        self.assertEqual(decision.risk, "high")
        self.assertEqual(decision.decided_by, "Data Owner (PR-02)")

    def test_escalation_reason_names_the_special_category(self):
        self.assertIn("ssn", self.decisions["REQ-002"].rationale)

    def test_leaked_pii_makes_an_otherwise_plain_dataset_escalate(self):
        """orders looks operational, but AG-03 found PII in notes — so the
        access decision follows the classification, not the table's reputation."""
        decision = self.decisions["REQ-003"]
        self.assertEqual(decision.decision, "escalated")

    def test_each_escalation_opens_an_issue_for_the_owner(self):
        escalated = [d for d in self.catalog.access_decisions if d.decision == "escalated"]
        access_issues = [i for i in self.catalog.issues if i.raised_by == "AG-08"]
        self.assertEqual(len(escalated), len(access_issues))

    def test_every_decision_is_recorded_for_audit(self):
        self.assertEqual(len(self.catalog.access_decisions), 3)


if __name__ == "__main__":
    unittest.main()
