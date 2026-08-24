"""Policy-as-code: declarative rules the catalog is evaluated against.

A rule names a scope (dataset or column), a `when` predicate selecting
which objects it applies to, and a single named `require` assertion that
those objects must satisfy. Adding a rule is a config edit; adding a new
kind of assertion is the only thing that needs code.

This is the substrate AG-07 runs on, and the source of truth for the
approved zones AG-03 used to hardcode.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.catalog import PolicyFinding


class PolicyEngine:
    def __init__(self, rules: list[dict], approved_zones: dict[str, set[str]]) -> None:
        self.rules = rules
        self.approved_zones = approved_zones

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        config = json.loads(Path(path).read_text())
        zones = {k: set(v) for k, v in config.get("approved_zones", {}).items()}
        return cls(config.get("rules", []), zones)

    # -- the assertion AG-03 consults --------------------------------------

    def is_approved_zone(self, dataset: str, column: str) -> bool:
        return column in self.approved_zones.get(dataset, set())

    def zones_map(self) -> dict[str, set[str]]:
        return self.approved_zones

    # -- evaluation --------------------------------------------------------

    def evaluate(self, catalog) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        for rule in self.rules:
            if rule["scope"] == "column":
                findings.extend(self._evaluate_columns(rule, catalog))
            elif rule["scope"] == "dataset":
                findings.extend(self._evaluate_datasets(rule, catalog))
        return findings

    def _evaluate_columns(self, rule: dict, catalog) -> list[PolicyFinding]:
        findings = []
        for dataset, column in catalog.all_columns():
            if not self._column_matches(rule.get("when", {}), column):
                continue
            if self._column_satisfies(rule["require"], dataset, column):
                continue
            findings.append(
                self._finding(rule, dataset.name, column.name, self._explain(rule["require"], column.name))
            )
        return findings

    def _evaluate_datasets(self, rule: dict, catalog) -> list[PolicyFinding]:
        findings = []
        for dataset in catalog.all_datasets():
            if not self._dataset_matches(rule.get("when", {}), dataset):
                continue
            if self._dataset_satisfies(rule["require"], dataset):
                continue
            findings.append(
                self._finding(rule, dataset.name, "-", self._explain(rule["require"], dataset.name))
            )
        return findings

    # -- predicates --------------------------------------------------------

    @staticmethod
    def _column_matches(when: dict, column) -> bool:
        for key, expected in when.items():
            if getattr(column, key, None) != expected:
                return False
        return True

    @staticmethod
    def _dataset_matches(when: dict, dataset) -> bool:
        for key, expected in when.items():
            if key == "has_restricted_column":
                if dataset.has_restricted_column() != expected:
                    return False
            elif getattr(dataset, key, None) != expected:
                return False
        return True

    def _column_satisfies(self, require: str, dataset, column) -> bool:
        if require == "approved_zone":
            return self.is_approved_zone(dataset.name, column.name)
        if require == "has_glossary_term":
            return column.glossary_term is not None
        raise ValueError(f"Unknown column assertion: {require}")

    @staticmethod
    def _dataset_satisfies(require: str, dataset) -> bool:
        if require == "has_owner":
            return dataset.owner is not None
        if require == "has_retention_class":
            return dataset.retention_class is not None
        raise ValueError(f"Unknown dataset assertion: {require}")

    # -- reporting ---------------------------------------------------------

    @staticmethod
    def _explain(require: str, target: str) -> str:
        return {
            "approved_zone": f"{target} holds restricted data but is not an approved location for it.",
            "has_glossary_term": f"{target} holds restricted data with no glossary term linked.",
            "has_owner": f"{target} has no accountable owner assigned.",
            "has_retention_class": f"{target} holds restricted data with no retention class set.",
        }[require]

    @staticmethod
    def _finding(rule: dict, dataset: str, column: str, detail: str) -> PolicyFinding:
        return PolicyFinding(
            rule_id=rule["id"],
            title=rule["title"],
            regulation=rule["regulation"],
            severity=rule["severity"],
            dataset=dataset,
            column=column,
            detail=detail,
        )
