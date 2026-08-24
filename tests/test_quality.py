import unittest

from helpers import full_run


class QualityAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run()

    def _result(self, dataset, column, dimension):
        return next(
            r
            for r in self.catalog.quality_results
            if r.dataset == dataset and r.column == column and r.dimension == dimension
        )

    def test_detects_the_duplicate_primary_key(self):
        result = self._result("customers", "customer_id", "uniqueness")
        self.assertFalse(result.passed)
        self.assertIn("1002", result.detail)

    def test_detects_the_missing_required_email(self):
        result = self._result("customers", "email", "completeness")
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 0.8)

    def test_clean_column_passes_completeness(self):
        self.assertTrue(self._result("orders", "order_id", "completeness").passed)

    def test_validity_passes_on_well_formed_dates(self):
        self.assertTrue(self._result("orders", "order_date", "validity").passed)

    def test_every_failure_becomes_a_tracked_issue(self):
        failures = [r for r in self.catalog.quality_results if not r.passed]
        quality_issues = [i for i in self.catalog.issues if i.raised_by == "AG-04"]
        self.assertEqual(len(failures), len(quality_issues))


if __name__ == "__main__":
    unittest.main()
