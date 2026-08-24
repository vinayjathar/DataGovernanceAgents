"""Cross-phase behaviour: the wiring itself, and agents reading each other's work."""

import unittest
from datetime import date

from helpers import CONFIG, MOCK_DATA, full_run

from governance.agents.orchestrator import Orchestrator
from governance.catalog import Catalog


class PhaseGatingTests(unittest.TestCase):
    def test_phase0_alone_does_not_activate_later_agents(self):
        """Rolling out Phase 0 must behave exactly as it did before Phase 1
        existed — later agents are constructed but never subscribed."""
        catalog = Catalog()
        Orchestrator(catalog, config_dir=CONFIG).run_phase0(MOCK_DATA)

        self.assertEqual(catalog.quality_results, [])
        self.assertEqual(catalog.policy_findings, [])
        self.assertEqual(catalog.access_decisions, [])
        self.assertTrue(all(i.raised_by == "AG-03" for i in catalog.issues))

    def test_phase0_runs_without_any_config_at_all(self):
        catalog = Catalog()
        Orchestrator(catalog).run_phase0(MOCK_DATA)
        self.assertEqual(len(catalog.datasets), 4)

    def test_later_phases_require_config(self):
        orchestrator = Orchestrator(Catalog())
        with self.assertRaises(RuntimeError):
            orchestrator.run_all(MOCK_DATA)


class CrossAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator, cls.catalog, cls.scorecard = full_run(as_of=date(2026, 8, 22))

    def test_classification_zones_come_from_the_policy_engine(self):
        self.assertIs(
            self.orchestrator.classification.policy_engine, self.orchestrator.policy_engine
        )

    def test_guardrail_decision_depends_on_lineage_built_by_another_agent(self):
        drop = next(f for f in self.catalog.guardrail_findings if f.op == "drop_column")
        self.assertEqual(drop.verdict, "block")
        self.assertTrue(self.catalog.lineage_edges)

    def test_issues_are_raised_by_six_different_agents(self):
        raisers = {i.raised_by for i in self.catalog.issues}
        self.assertEqual(raisers, {"AG-03", "AG-04", "AG-07", "AG-08", "AG-10", "AG-13"})

    def test_issue_ids_are_unique(self):
        ids = [i.id for i in self.catalog.issues]
        self.assertEqual(len(ids), len(set(ids)))


class AuditAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator, cls.catalog, cls.scorecard = full_run(as_of=date(2026, 8, 22))

    def test_audit_observes_events_from_every_agent(self):
        events = self.orchestrator.audit.event_summary()
        for expected in (
            "dataset.discovered",
            "quality.violation",
            "policy.violation",
            "lineage.built",
            "guardrail.checked",
        ):
            self.assertIn(expected, events)

    def test_scorecard_reports_full_classification_coverage(self):
        self.assertEqual(self.scorecard["coverage"]["columns_classified"], 100.0)

    def test_scorecard_reports_the_unowned_dataset_as_a_coverage_gap(self):
        self.assertEqual(self.scorecard["coverage"]["ownership_assigned"], 75.0)

    def test_scorecard_counts_open_issues_by_raising_agent(self):
        self.assertEqual(
            sum(self.scorecard["issues"]["by_raising_agent"].values()),
            self.scorecard["issues"]["open"],
        )

    def test_audit_writes_no_governance_decisions_of_its_own(self):
        """AG-12 is observation-only — that independence is what makes its
        trail usable as audit evidence."""
        self.assertEqual([i for i in self.catalog.issues if i.raised_by == "AG-12"], [])


if __name__ == "__main__":
    unittest.main()
