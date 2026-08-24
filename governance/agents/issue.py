"""AG-11 · Issue & Remediation.

Single intake for every finding any agent raises. Each producing agent
publishes its own event type; this agent is the only place that decides
who a finding gets assigned to and how long they have to fix it, so
that routing lives in one file rather than smeared across the fleet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from governance.agents.base import Agent, Authority
from governance.catalog import Issue

# event type -> (issue kind, severity, assignee persona, SLA hours)
INTAKE_ROUTING = {
    "classification.exception": ("unapproved_pii_location", "high", "Data Steward (PR-03)", 24),
    "quality.violation": ("quality_rule_failed", "medium", "Data Steward (PR-03)", 72),
    "policy.violation": ("policy_breach", "high", "Compliance Officer (PR-06)", 48),
    "retention.due": ("retention_due", "medium", "Data Owner (PR-02)", 168),
    "access.escalated": ("access_pending_approval", "medium", "Data Owner (PR-02)", 24),
    "training.blocked": ("ai_usage_blocked", "high", "Compliance Officer (PR-06)", 24),
}


class IssueAgent(Agent):
    agent_id = "AG-11"
    name = "Issue & Remediation"
    authority = Authority.AUTO_ACT  # ticket lifecycle only, no data changes

    def __init__(self, bus, catalog) -> None:
        super().__init__(bus, catalog)
        self._counter = 0

    # -- intake ------------------------------------------------------------

    def handle_exception(self, payload: dict) -> None:
        """AG-03 classification exceptions (Phase 0 path)."""
        self._open(
            "classification.exception",
            dataset=payload["dataset"],
            column=payload["column"],
            detail=(
                f"Detected {', '.join(payload['kinds'])} in "
                f"{payload['dataset']}.{payload['column']}, which policy does not "
                f"list as an approved location for sensitive data."
            ),
            raised_by="AG-03",
        )

    def handle_quality_violation(self, payload: dict) -> None:
        self._open(
            "quality.violation",
            dataset=payload["dataset"],
            column=payload["column"],
            detail=payload["detail"],
            raised_by="AG-04",
        )

    def handle_policy_violation(self, payload: dict) -> None:
        self._open(
            "policy.violation",
            dataset=payload["dataset"],
            column=payload["column"],
            detail=f"[{payload['rule_id']}] {payload['detail']} ({payload['regulation']})",
            raised_by="AG-07",
            severity=payload.get("severity"),
        )

    def handle_retention_due(self, payload: dict) -> None:
        self._open(
            "retention.due",
            dataset=payload["dataset"],
            column="-",
            detail=payload["detail"],
            raised_by="AG-10",
        )

    def handle_access_escalated(self, payload: dict) -> None:
        self._open(
            "access.escalated",
            dataset=payload["dataset"],
            column="-",
            detail=(
                f"{payload['request_id']} from {payload['requester']} needs owner "
                f"approval: {payload['rationale']}"
            ),
            raised_by="AG-08",
        )

    def handle_training_blocked(self, payload: dict) -> None:
        self._open(
            "training.blocked",
            dataset=payload["model"],
            column=", ".join(payload["blocking_columns"]) or "-",
            detail=payload["rationale"],
            raised_by="AG-13",
        )

    # -- ticket creation ---------------------------------------------------

    def _open(
        self,
        event_type: str,
        *,
        dataset: str,
        column: str,
        detail: str,
        raised_by: str,
        severity: str | None = None,
    ) -> Issue:
        kind, default_severity, assignee, sla = INTAKE_ROUTING[event_type]
        self._counter += 1
        issue = Issue(
            id=f"ISS-{self._counter:03d}",
            dataset=dataset,
            column=column,
            kind=kind,
            detail=detail,
            assigned_to=assignee,
            status="open",
            opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sla_hours=sla,
            severity=severity or default_severity,
            raised_by=raised_by,
        )
        self.catalog.add_issue(issue)
        return issue
