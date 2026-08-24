import unittest

from helpers import full_run


class GuardrailAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run()
        cls.findings = {f.target: f for f in cls.catalog.guardrail_findings}

    def test_blocks_a_new_pii_column_in_an_unapproved_table(self):
        finding = self.findings["orders.customer_ssn_backup"]
        self.assertEqual(finding.verdict, "block")
        self.assertIn("ssn", finding.detail)

    def test_blocks_dropping_a_column_with_downstream_consumers(self):
        finding = self.findings["orders.notes"]
        self.assertEqual(finding.verdict, "block")
        self.assertIn("orders_enriched", finding.detail)

    def test_passes_a_documented_non_sensitive_column(self):
        self.assertEqual(self.findings["products.supplier_name"].verdict, "pass")

    def test_block_message_tells_the_developer_how_to_fix_it(self):
        self.assertIn("approved zone", self.findings["orders.customer_ssn_backup"].detail)

    def test_guardrail_does_not_open_tickets(self):
        """A failing CI check belongs in the PR, not in the steward's queue."""
        self.assertEqual([i for i in self.catalog.issues if i.raised_by == "AG-14"], [])


if __name__ == "__main__":
    unittest.main()
