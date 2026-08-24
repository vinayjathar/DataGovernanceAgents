import unittest

from helpers import full_run


class LineageAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator, cls.catalog, _ = full_run()

    def test_derived_nodes_are_created_for_pipeline_outputs(self):
        self.assertEqual(self.catalog.lineage_nodes["orders_enriched"].kind, "derived")
        self.assertEqual(self.catalog.lineage_nodes["customers"].kind, "source")

    def test_restriction_propagates_to_a_derived_dataset(self):
        """orders.notes is restricted, so anything built from orders is too —
        even though nothing labeled the derived table."""
        self.assertEqual(
            self.catalog.lineage_nodes["orders_enriched"].inherited_sensitivity, "restricted"
        )

    def test_restriction_propagates_transitively(self):
        report = self.catalog.lineage_nodes["rpt_exec_revenue"]
        self.assertEqual(report.inherited_sensitivity, "restricted")
        self.assertIn("ssn", report.inherited_tags)

    def test_impact_analysis_returns_transitive_downstream(self):
        impact = set(self.orchestrator.lineage.impact_of("orders"))
        self.assertEqual(impact, {"orders_enriched", "customer_360", "rpt_exec_revenue"})

    def test_column_level_consumers_are_tracked(self):
        self.assertEqual(
            self.orchestrator.lineage.column_consumers("orders", "notes"), ["orders_enriched"]
        )

    def test_unconsumed_column_has_no_consumers(self):
        self.assertEqual(self.orchestrator.lineage.column_consumers("orders", "order_date"), [])


if __name__ == "__main__":
    unittest.main()
