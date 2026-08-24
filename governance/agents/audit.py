"""AG-12 · Audit & Monitoring.

Subscribes to every event rather than to specific types, so anything a
new agent publishes lands in the trail without this file changing. That
wildcard tap is the whole point: an audit trail assembled from what the
agents were asked to report would only ever show what someone
remembered to wire up.

Observation only — this agent never writes to a dataset or a decision,
which is what lets an auditor treat its trail as independent.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from governance.agents.base import Agent, Authority


class AuditAgent(Agent):
    agent_id = "AG-12"
    name = "Audit & Monitoring"
    authority = Authority.AUTO_ACT  # observation only

    def __init__(self, bus, catalog) -> None:
        super().__init__(bus, catalog)
        self.trail: list[dict] = []

    def observe(self, event_type: str, payload: dict) -> None:
        self.trail.append(
            {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event": event_type,
                "subject": payload.get("dataset") or payload.get("model") or payload.get("pull_request") or "-",
            }
        )

    # -- scorecard ---------------------------------------------------------

    def build_scorecard(self, compliance_rate: float | None = None) -> dict:
        datasets = self.catalog.all_datasets()
        columns = [c for _, c in self.catalog.all_columns()]

        owned = [d for d in datasets if d.owner]
        classified = [c for c in columns if c.sensitivity != "unclassified"]
        termed = [c for c in columns if c.glossary_term]
        quality = self.catalog.quality_results
        passing = [q for q in quality if q.passed]

        scorecard = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "coverage": {
                "datasets_cataloged": len(datasets),
                "ownership_assigned": self._pct(len(owned), len(datasets)),
                "columns_classified": self._pct(len(classified), len(columns)),
                "glossary_linked": self._pct(len(termed), len(columns)),
            },
            "quality": {
                "checks_run": len(quality),
                "pass_rate": self._pct(len(passing), len(quality)),
            },
            "compliance": {
                "policy_findings": len(self.catalog.policy_findings),
                "rule_compliance_rate": compliance_rate,
                "findings_by_severity": dict(
                    Counter(f.severity for f in self.catalog.policy_findings)
                ),
            },
            "issues": {
                "open": len(self.catalog.open_issues()),
                "by_severity": dict(Counter(i.severity for i in self.catalog.open_issues())),
                "by_raising_agent": dict(Counter(i.raised_by for i in self.catalog.open_issues())),
            },
            "risk": {
                "high_risk_datasets": [
                    r.subject for r in self.catalog.risk_assessments if r.band == "high"
                ],
            },
            "audit_trail_events": len(self.trail),
        }
        self.catalog.set_scorecard(scorecard)
        return scorecard

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        if not denominator:
            return 0.0
        return round(100 * numerator / denominator, 1)

    def event_summary(self) -> dict[str, int]:
        return dict(Counter(entry["event"] for entry in self.trail))
