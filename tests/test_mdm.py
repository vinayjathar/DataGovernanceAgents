import unittest

from helpers import full_run

from governance.agents.mdm import name_similarity, normalize_phone


class MatchHelperTests(unittest.TestCase):
    def test_phone_normalization_strips_formatting(self):
        self.assertEqual(normalize_phone("415-555-0199"), "4155550199")

    def test_name_similarity_is_high_for_a_spelling_variant(self):
        self.assertGreater(name_similarity("John Doe", "Jon Doe"), 0.82)

    def test_name_similarity_is_low_for_different_people(self):
        self.assertLess(name_similarity("Wei Chen", "Priya Nair"), 0.5)


class MDMAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.catalog, _ = full_run()
        cls.records = {r.id: r for r in cls.catalog.golden_records}

    def _record_containing(self, ref):
        return next(r for r in self.catalog.golden_records if ref in r.members)

    def test_matches_the_same_person_across_two_systems_by_email(self):
        record = self._record_containing("customers:1001")
        self.assertIn("legacy_customers:CUST-1001", record.members)
        self.assertEqual(record.match_rule, "exact_email")

    def test_matches_on_phone_and_similar_name_when_email_is_missing(self):
        record = self._record_containing("customers:1003")
        self.assertIn("legacy_customers:CUST-1003", record.members)
        self.assertEqual(record.match_rule, "phone_and_similar_name")

    def test_collapses_the_duplicate_row_within_one_source(self):
        record = self._record_containing("customers:1002")
        self.assertEqual(record.members.count("customers:1002"), 2)

    def test_survivorship_fills_gaps_from_the_other_source(self):
        """customers:1003 has no email; the legacy record has no better one
        either, so the merged phone is what survives."""
        record = self._record_containing("customers:1003")
        self.assertEqual(record.attributes["phone"], "212-555-0111")
        self.assertEqual(record.attributes["source_count"], "2")

    def test_unmatched_record_stays_a_singleton(self):
        record = self._record_containing("legacy_customers:CUST-9001")
        self.assertEqual(record.match_rule, "singleton")
        self.assertEqual(len(record.members), 1)

    def test_golden_records_are_proposed_not_merged(self):
        self.assertTrue(all(r.status == "proposed" for r in self.catalog.golden_records))


if __name__ == "__main__":
    unittest.main()
