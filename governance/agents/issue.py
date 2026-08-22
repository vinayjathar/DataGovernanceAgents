"""AG-11 · Issue & Remediation (lightweight).

Turns every classification.exception into a tracked ticket assigned to
the Data Steward, with an SLA clock — the same shape workflow 5.3 in the
design registry describes, minus the actual access-restriction call
(that's AG-08's job and out of scope for this phase-0 slice).
"""

from __future__ import annotations

from datetime import datetime, timezone

from governance.agents.base import Agent, Authority
from governance.catalog import Issue

DEFAULT_SLA_HOURS = 24


class IssueAgent(Agent):
    agent_id = "AG-11"
    name = "Issue & Remediation"
    authority = Authority.AUTO_ACT  # ticket lifecycle only, no data changes

    def __init__(self, bus, catalog) -> None:
        super().__init__(bus, catalog)
        self._counter = 0

    def handle_exception(self, payload: dict) -> None:
        self._counter += 1
        issue = Issue(
            id=f"ISS-{self._counter:03d}",
            dataset=payload["dataset"],
            column=payload["column"],
            kind="unapproved_pii_location",
            detail=(
                f"Detected {', '.join(payload['kinds'])} in "
                f"{payload['dataset']}.{payload['column']}, which policy does not "
                f"list as an approved location for sensitive data."
            ),
            assigned_to="Data Steward (PR-03)",
            status="open",
            opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sla_hours=DEFAULT_SLA_HOURS,
        )
        self.catalog.add_issue(issue)
