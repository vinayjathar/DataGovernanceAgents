"""AG-08 · Access & Entitlement.

Workflow 5.2 from the design registry. Every request is scored against
what the requested dataset actually holds — as classified by AG-03, not
as declared by the requester. Low risk closes the loop here (auto-act);
anything touching a special category escalates to the Data Owner and
waits.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import AccessDecision

# Regulatory tags that always require a human decision, no matter the purpose.
SPECIAL_CATEGORY = {"ssn"}


class AccessAgent(Agent):
    agent_id = "AG-08"
    name = "Access & Entitlement"
    authority = Authority.AUTO_ACT  # below threshold; escalates above it

    @staticmethod
    def load_requests(path: str | Path) -> list[dict]:
        return json.loads(Path(path).read_text())["requests"]

    def process(self, requests: list[dict]) -> list[AccessDecision]:
        return [self._decide(request) for request in requests]

    def _decide(self, request: dict) -> AccessDecision:
        entry = self.catalog.datasets.get(request["dataset"])
        if entry is None:
            return self._record(request, "denied", "unknown", "Dataset is not in the catalog.")

        restricted = [c for c in entry.columns if c.sensitivity == "restricted"]
        tags = {tag for column in restricted for tag in column.regulatory_tags}

        if tags & SPECIAL_CATEGORY:
            return self._escalate(
                request,
                "high",
                f"{request['dataset']} contains special-category data "
                f"({', '.join(sorted(tags & SPECIAL_CATEGORY))}); owner approval required.",
            )

        if restricted:
            return self._escalate(
                request,
                "moderate",
                f"{request['dataset']} contains {len(restricted)} restricted column(s) "
                f"tagged {', '.join(sorted(tags))}; owner approval required.",
            )

        return self._record(
            request,
            "auto-approved",
            "low",
            f"{request['dataset']} holds no restricted columns; "
            f"granted under standing policy for purpose '{request['purpose']}'.",
        )

    def _escalate(self, request: dict, risk: str, rationale: str) -> AccessDecision:
        decision = self._record(request, "escalated", risk, rationale, decided_by="Data Owner (PR-02)")
        self.bus.publish(
            "access.escalated",
            {
                "request_id": request["id"],
                "requester": request["requester"],
                "dataset": request["dataset"],
                "rationale": rationale,
            },
        )
        return decision

    def _record(
        self,
        request: dict,
        decision: str,
        risk: str,
        rationale: str,
        decided_by: str = "AG-08 (auto)",
    ) -> AccessDecision:
        record = AccessDecision(
            request_id=request["id"],
            requester=request["requester"],
            dataset=request["dataset"],
            purpose=request["purpose"],
            decision=decision,
            risk=risk,
            rationale=rationale,
            decided_by=decided_by,
        )
        self.catalog.record("access_decisions", record)
        if decision == "auto-approved":
            self.bus.publish(
                "access.granted",
                {"request_id": request["id"], "dataset": request["dataset"]},
            )
        return record
