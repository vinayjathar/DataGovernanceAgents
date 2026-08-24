"""AG-07 · Policy & Compliance.

Runs the PolicyEngine over the whole catalog and publishes one
policy.violation per failing rule. It evaluates rather than interprets:
the rules live in config/policy_rules.json, so a compliance officer
changes policy by editing config, not code.

Runs last in a pass, because its rules assert over what the earlier
agents wrote — sensitivity from AG-03, glossary terms from AG-06,
ownership and retention class from the owner registry.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority


class PolicyAgent(Agent):
    agent_id = "AG-07"
    name = "Policy & Compliance"
    authority = Authority.RECOMMEND

    def __init__(self, bus, catalog, engine) -> None:
        super().__init__(bus, catalog)
        self.engine = engine

    @staticmethod
    def load_owners(path: str | Path) -> dict:
        return json.loads(Path(path).read_text())

    def apply_owner_registry(self, owners: dict) -> None:
        """Stamp ownership metadata onto the catalog before evaluating.

        Datasets missing from the registry are left unowned on purpose —
        POL-002 is what turns that gap into a tracked finding.
        """
        for dataset_name, meta in owners.items():
            if dataset_name in self.catalog.datasets:
                self.catalog.update_dataset(
                    dataset_name,
                    owner=meta.get("owner"),
                    domain=meta.get("domain"),
                    retention_class=meta.get("retention_class"),
                )

    def evaluate_catalog(self) -> list:
        findings = self.engine.evaluate(self.catalog)
        for finding in findings:
            self.catalog.record("policy_findings", finding)
            self.bus.publish(
                "policy.violation",
                {
                    "rule_id": finding.rule_id,
                    "dataset": finding.dataset,
                    "column": finding.column,
                    "detail": finding.detail,
                    "regulation": finding.regulation,
                    "severity": finding.severity,
                },
            )
        return findings

    def compliance_rate(self) -> float:
        """Share of evaluated rules with no open finding — feeds AG-12."""
        total = len(self.engine.rules)
        if not total:
            return 1.0
        breached = {f.rule_id for f in self.catalog.policy_findings}
        return round((total - len(breached)) / total, 3)
