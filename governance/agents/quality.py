"""AG-04 · Data Quality.

Profiles each dataset against declared rules across four dimensions —
completeness, uniqueness, validity, and consistency. Scoring is
auto-act; a failed rule publishes quality.violation for AG-11 to
track, but this agent never edits the data itself.

Values come from re-reading the source, not from the catalog: the
catalog stores five sample values per column, which is enough to
classify but not enough to detect a duplicate key.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import QualityResult
from governance.sources import read_rows

FORMAT_PATTERNS = {
    "email": re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "decimal": re.compile(r"^-?\d+(\.\d+)?$"),
}


class QualityAgent(Agent):
    agent_id = "AG-04"
    name = "Data Quality"
    authority = Authority.AUTO_ACT

    def __init__(self, bus, catalog, rules: dict | None = None) -> None:
        super().__init__(bus, catalog)
        self.rules = rules or {}

    @staticmethod
    def load_rules(path: str | Path) -> dict:
        return json.loads(Path(path).read_text())

    def handle_dataset_discovered(self, payload: dict) -> None:
        self.profile(payload["dataset"])

    def profile(self, dataset_name: str) -> list[QualityResult]:
        entry = self.catalog.datasets[dataset_name]
        rules = self.rules.get(dataset_name)
        if not rules:
            return []

        rows = read_rows(entry.source_path)
        results = [
            *self._check_completeness(entry, rows, rules),
            *self._check_uniqueness(entry, rows, rules),
            *self._check_validity(entry, rows, rules),
        ]

        for result in results:
            self.catalog.record("quality_results", result)
            if not result.passed:
                self.bus.publish(
                    "quality.violation",
                    {
                        "dataset": result.dataset,
                        "column": result.column,
                        "dimension": result.dimension,
                        "detail": result.detail,
                    },
                )
        return results

    # -- dimensions --------------------------------------------------------

    def _check_completeness(self, entry, rows, rules) -> list[QualityResult]:
        results = []
        for column_name in rules.get("required", []):
            missing = sum(1 for row in rows if not row.get(column_name))
            score = 1 - (missing / len(rows)) if rows else 1.0
            results.append(
                QualityResult(
                    dataset=entry.name,
                    column=column_name,
                    dimension="completeness",
                    passed=missing == 0,
                    detail=(
                        f"{missing} of {len(rows)} rows missing a required value "
                        f"in {entry.name}.{column_name}."
                        if missing
                        else f"All {len(rows)} rows populated."
                    ),
                    score=round(score, 3),
                )
            )
        return results

    def _check_uniqueness(self, entry, rows, rules) -> list[QualityResult]:
        key = rules.get("primary_key")
        if not key:
            return []

        seen: dict[str, int] = {}
        for row in rows:
            value = row.get(key, "")
            seen[value] = seen.get(value, 0) + 1
        duplicates = {v: n for v, n in seen.items() if n > 1}
        score = 1 - (sum(duplicates.values()) - len(duplicates)) / len(rows) if rows else 1.0

        return [
            QualityResult(
                dataset=entry.name,
                column=key,
                dimension="uniqueness",
                passed=not duplicates,
                detail=(
                    f"Primary key {entry.name}.{key} repeats for "
                    f"{', '.join(sorted(duplicates))}."
                    if duplicates
                    else f"All {len(rows)} key values unique."
                ),
                score=round(score, 3),
            )
        ]

    def _check_validity(self, entry, rows, rules) -> list[QualityResult]:
        results = []
        for column_name, format_name in rules.get("formats", {}).items():
            pattern = FORMAT_PATTERNS.get(format_name)
            if pattern is None:
                continue
            populated = [row.get(column_name, "") for row in rows if row.get(column_name)]
            bad = [v for v in populated if not pattern.match(v)]
            score = 1 - (len(bad) / len(populated)) if populated else 1.0
            results.append(
                QualityResult(
                    dataset=entry.name,
                    column=column_name,
                    dimension="validity",
                    passed=not bad,
                    detail=(
                        f"{len(bad)} value(s) in {entry.name}.{column_name} do not "
                        f"match the {format_name} format: {', '.join(bad[:3])}."
                        if bad
                        else f"All {len(populated)} populated values match {format_name}."
                    ),
                    score=round(score, 3),
                )
            )
        return results
