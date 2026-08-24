import unittest

from helpers import full_run


class RiskAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run()
        cls.assessments = {a.subject: a for a in cls.catalog.risk_assessments}
        cls.training = {t.model: t for t in cls.catalog.training_decisions}

    def test_dataset_with_special_category_and_fan_out_scores_high(self):
        assessment = self.assessments["customers"]
        self.assertEqual(assessment.band, "high")
        self.assertTrue(any("special-category" in d for d in assessment.drivers))

    def test_clean_reference_data_scores_low(self):
        self.assertEqual(self.assessments["products"].band, "low")

    def test_missing_owner_is_a_scored_risk_driver(self):
        drivers = self.assessments["legacy_customers"].drivers
        self.assertIn("no accountable owner", drivers)

    def test_downstream_fan_out_raises_the_score(self):
        """The same sensitivity is more risk when it travels further, so the
        score must read lineage rather than the table alone."""
        self.assertTrue(
            any("downstream" in d for d in self.assessments["orders"].drivers)
        )

    def test_training_on_special_category_data_is_blocked(self):
        decision = self.training["churn_propensity_v3"]
        self.assertEqual(decision.decision, "blocked")
        self.assertIn("customers.ssn", decision.blocking_columns)

    def test_blocked_training_raises_a_compliance_issue(self):
        blocked = [t for t in self.catalog.training_decisions if t.decision == "blocked"]
        risk_issues = [i for i in self.catalog.issues if i.raised_by == "AG-13"]
        self.assertEqual(len(blocked), len(risk_issues))


if __name__ == "__main__":
    unittest.main()
