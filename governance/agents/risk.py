"""AG-13 · Risk & AI-Governance.

Two jobs that share one risk model.

Scoring: a dataset's risk is not just how sensitive it is but how far
that sensitivity travels — so the score reads AG-05's lineage graph for
downstream fan-out and AG-08's decisions for how widely it is shared.
A restricted table nobody consumes is a smaller problem than a
restricted table feeding four dashboards.

Training gate: authority is escalate. Special-category data blocks a
training run outright; other restricted data is approved only on
condition of masking.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import RiskAssessment, TrainingDecision

BLOCKING_TAGS = {"ssn"}
MASKABLE_TAGS = {"email", "phone", "name"}


class RiskAgent(Agent):
    agent_id = "AG-13"
    name = "Risk & AI-Governance"
    authority = Authority.ESCALATE

    @staticmethod
    def load_manifests(path: str | Path) -> list[dict]:
        return json.loads(Path(path).read_text())["manifests"]

    # -- risk scoring ------------------------------------------------------

    def assess_all(self) -> list[RiskAssessment]:
        return [self.assess(entry.name) for entry in self.catalog.all_datasets()]

    def assess(self, dataset_name: str) -> RiskAssessment:
        entry = self.catalog.datasets[dataset_name]
        restricted = [c for c in entry.columns if c.sensitivity == "restricted"]
        tags = {t for c in restricted for t in c.regulatory_tags}
        downstream = self.catalog.downstream_of(dataset_name)
        grants = [
            d
            for d in self.catalog.access_decisions
            if d.dataset == dataset_name and d.decision == "auto-approved"
        ]

        score = 0
        drivers = []

        if restricted:
            score += 10 * len(restricted)
            drivers.append(f"{len(restricted)} restricted column(s)")
        if tags & BLOCKING_TAGS:
            score += 25
            drivers.append(f"special-category data ({', '.join(sorted(tags & BLOCKING_TAGS))})")
        if downstream:
            score += 8 * len(downstream)
            drivers.append(f"flows to {len(downstream)} downstream asset(s)")
        if grants:
            score += 5 * len(grants)
            drivers.append(f"{len(grants)} standing auto-approved grant(s)")
        if entry.owner is None:
            score += 15
            drivers.append("no accountable owner")

        assessment = RiskAssessment(
            subject=dataset_name,
            score=score,
            band=self._band(score),
            drivers=drivers or ["no risk drivers detected"],
        )
        self.catalog.record("risk_assessments", assessment)
        return assessment

    @staticmethod
    def _band(score: int) -> str:
        if score >= 60:
            return "high"
        if score >= 25:
            return "moderate"
        return "low"

    # -- AI training gate --------------------------------------------------

    def review_training(self, manifests: list[dict]) -> list[TrainingDecision]:
        decisions = []
        for manifest in manifests:
            decisions.append(self._review_one(manifest))
        return decisions

    def _review_one(self, manifest: dict) -> TrainingDecision:
        blocking, maskable = [], []
        for dataset_name in manifest["datasets"]:
            entry = self.catalog.datasets.get(dataset_name)
            if entry is None:
                continue
            for column in entry.columns:
                if column.sensitivity != "restricted":
                    continue
                tags = set(column.regulatory_tags)
                if tags & BLOCKING_TAGS:
                    blocking.append(f"{dataset_name}.{column.name}")
                elif tags & MASKABLE_TAGS:
                    maskable.append(f"{dataset_name}.{column.name}")

        if blocking:
            decision = TrainingDecision(
                model=manifest["model"],
                decision="blocked",
                blocking_columns=blocking,
                rationale=(
                    f"Training set for {manifest['model']} includes special-category data "
                    f"({', '.join(blocking)}). Blocked pending Compliance review."
                ),
            )
            self.bus.publish(
                "training.blocked",
                {
                    "model": decision.model,
                    "blocking_columns": decision.blocking_columns,
                    "rationale": decision.rationale,
                },
            )
        elif maskable:
            decision = TrainingDecision(
                model=manifest["model"],
                decision="approved_with_masking",
                blocking_columns=maskable,
                rationale=(
                    f"Approved on condition that {', '.join(maskable)} are masked or "
                    f"tokenized before {manifest['model']} training."
                ),
            )
        else:
            decision = TrainingDecision(
                model=manifest["model"],
                decision="approved",
                blocking_columns=[],
                rationale=f"No restricted columns in the {manifest['model']} training set.",
            )

        self.catalog.record("training_decisions", decision)
        return decision
