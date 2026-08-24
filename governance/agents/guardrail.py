"""AG-14 · Developer Guardrail.

Governance shifted left into CI. Runs against a proposed schema diff
before merge, where a fix costs a line of code, rather than after
deploy, where it costs a remediation ticket and a breach notification.

Blocks on two things the developer cannot see from inside the PR: that
a new column name matches a PII pattern in a table not approved to hold
it, and that a column being dropped is consumed by a downstream
pipeline (asked of AG-05's graph, not guessed).
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.agents.classification import detect_kinds
from governance.catalog import GuardrailFinding


class GuardrailAgent(Agent):
    agent_id = "AG-14"
    name = "Developer Guardrail"
    authority = Authority.AUTO_ACT  # blocks a merge; never edits the branch

    def __init__(self, bus, catalog, policy_engine=None) -> None:
        super().__init__(bus, catalog)
        self.policy_engine = policy_engine

    @staticmethod
    def load_change(path: str | Path) -> dict:
        return json.loads(Path(path).read_text())

    def check(self, change_set: dict) -> list[GuardrailFinding]:
        pr = change_set["pull_request"]
        findings = []

        for change in change_set["changes"]:
            if change["op"] == "add_column":
                findings.append(self._check_add(pr, change))
            elif change["op"] == "drop_column":
                findings.append(self._check_drop(pr, change))

        for finding in findings:
            self.catalog.record("guardrail_findings", finding)

        blocked = [f for f in findings if f.verdict == "block"]
        self.bus.publish(
            "guardrail.checked",
            {"pull_request": pr, "blocked": len(blocked), "checks": len(findings)},
        )
        return findings

    # -- checks ------------------------------------------------------------

    def _check_add(self, pr: str, change: dict) -> GuardrailFinding:
        dataset, column = change["dataset"], change["column"]
        target = f"{dataset}.{column}"
        kinds = detect_kinds(column, [])

        if kinds and not self._approved(dataset, column):
            return GuardrailFinding(
                pull_request=pr,
                op="add_column",
                target=target,
                verdict="block",
                detail=(
                    f"New column {target} looks like {', '.join(sorted(kinds))} data, but "
                    f"{dataset} is not an approved location for it. Add it to the approved "
                    f"zone in policy, or store the value in {dataset}'s approved parent."
                ),
            )

        if not change.get("description"):
            return GuardrailFinding(
                pull_request=pr,
                op="add_column",
                target=target,
                verdict="warn",
                detail=f"{target} has no description; AG-06 will have to draft one for review.",
            )

        return GuardrailFinding(
            pull_request=pr,
            op="add_column",
            target=target,
            verdict="pass",
            detail=f"{target} is documented and holds no detected sensitive data.",
        )

    def _check_drop(self, pr: str, change: dict) -> GuardrailFinding:
        dataset, column = change["dataset"], change["column"]
        target = f"{dataset}.{column}"
        consumers = self.catalog.consumers_of_column(dataset, column)

        if consumers:
            return GuardrailFinding(
                pull_request=pr,
                op="drop_column",
                target=target,
                verdict="block",
                detail=(
                    f"{target} is consumed downstream by {', '.join(consumers)}. "
                    f"Dropping it breaks those pipelines; update them first or get "
                    f"impact sign-off from the Data Owner."
                ),
            )

        return GuardrailFinding(
            pull_request=pr,
            op="drop_column",
            target=target,
            verdict="pass",
            detail=f"{target} has no known downstream consumers.",
        )

    def _approved(self, dataset: str, column: str) -> bool:
        if self.policy_engine is None:
            return False
        return self.policy_engine.is_approved_zone(dataset, column)
