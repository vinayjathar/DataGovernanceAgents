import unittest

from helpers import full_run


class GlossaryAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator, cls.catalog, _ = full_run()

    def _column(self, dataset, column):
        return self.catalog.datasets[dataset].column(column)

    def test_links_a_column_to_its_term_by_exact_name(self):
        self.assertEqual(self._column("orders", "amount").glossary_term, "Order Amount")

    def test_links_a_column_to_its_term_by_synonym(self):
        self.assertEqual(
            self._column("legacy_customers", "email_address").glossary_term, "Email Address"
        )

    def test_links_land_as_draft_pending_steward_approval(self):
        self.assertEqual(self._column("orders", "amount").term_status, "draft")

    def test_unmatched_columns_get_a_drafted_definition(self):
        drafted = {(d["dataset"], d["column"]) for d in self.orchestrator.glossary.drafted}
        self.assertIn(("customers", "country"), drafted)

    def test_detects_a_term_whose_columns_disagree_on_type(self):
        conflicts = {c["term"]: c for c in self.orchestrator.glossary.conflicts}
        self.assertIn("Customer Identifier", conflicts)
        self.assertEqual(conflicts["Customer Identifier"]["types"], ["integer", "string"])

    def test_consistent_term_is_not_reported_as_a_conflict(self):
        conflicted = {c["term"] for c in self.orchestrator.glossary.conflicts}
        self.assertNotIn("Order Amount", conflicted)

    def test_drafts_never_quote_values_from_a_sensitive_column(self):
        """A glossary is published to consumers — an illustrative 'e.g.' on a
        restricted column would republish the PII the system exists to contain."""
        ssn_draft = next(
            d
            for d in self.orchestrator.glossary.drafted
            if (d["dataset"], d["column"]) == ("customers", "ssn")
        )
        self.assertNotIn("521-11-4487", ssn_draft["proposed_definition"])
        self.assertIn("withheld", ssn_draft["proposed_definition"])

    def test_drafts_do_quote_values_from_a_safe_column(self):
        country_draft = next(
            d
            for d in self.orchestrator.glossary.drafted
            if (d["dataset"], d["column"]) == ("customers", "country")
        )
        self.assertIn("US", country_draft["proposed_definition"])


if __name__ == "__main__":
    unittest.main()
