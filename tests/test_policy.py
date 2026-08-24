import unittest

from helpers import CONFIG, full_run

from governance.policy_engine import PolicyEngine


class PolicyEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator, cls.catalog, _ = full_run()
        cls.findings = cls.catalog.policy_findings

    def _by_rule(self, rule_id):
        return [f for f in self.findings if f.rule_id == rule_id]

    def test_pol001_flags_pii_outside_an_approved_zone(self):
        findings = self._by_rule("POL-001")
        self.assertEqual([(f.dataset, f.column) for f in findings], [("orders", "notes")])

    def test_pol001_does_not_flag_approved_pii(self):
        flagged = {(f.dataset, f.column) for f in self._by_rule("POL-001")}
        self.assertNotIn(("customers", "email"), flagged)
        self.assertNotIn(("customers", "ssn"), flagged)

    def test_pol002_flags_the_dataset_missing_from_the_owner_registry(self):
        self.assertEqual([f.dataset for f in self._by_rule("POL-002")], ["legacy_customers"])

    def test_pol003_flags_restricted_data_with_no_retention_class(self):
        self.assertEqual([f.dataset for f in self._by_rule("POL-003")], ["legacy_customers"])

    def test_findings_carry_their_regulatory_basis(self):
        self.assertIn("GDPR", self._by_rule("POL-001")[0].regulation)

    def test_approved_zones_come_from_config_not_code(self):
        engine = PolicyEngine.from_file(CONFIG / "policy_rules.json")
        self.assertTrue(engine.is_approved_zone("customers", "ssn"))
        self.assertFalse(engine.is_approved_zone("orders", "notes"))

    def test_compliance_rate_is_the_share_of_unbreached_rules(self):
        breached = {f.rule_id for f in self.findings}
        expected = (len(self.orchestrator.policy.engine.rules) - len(breached)) / len(
            self.orchestrator.policy.engine.rules
        )
        self.assertAlmostEqual(self.orchestrator.policy.compliance_rate(), expected, places=3)


if __name__ == "__main__":
    unittest.main()
