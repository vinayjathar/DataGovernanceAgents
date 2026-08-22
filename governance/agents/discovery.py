"""AG-02 · Discovery & Cataloging.

Scans a directory of source files, infers schema, and registers each
one in the catalog. Authority: auto-act — registration is additive and
reversible, so nothing here waits for a human.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import DatasetColumn, DatasetEntry


def _infer_single_type(value: str) -> str:
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    try:
        float(value)
        return "float"
    except ValueError:
        pass
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return "date"
    except ValueError:
        pass
    return "string"


def infer_column_type(values: list[str]) -> str:
    non_empty = [v for v in values if v != ""]
    if not non_empty:
        return "string"
    votes = Counter(_infer_single_type(v) for v in non_empty)
    return votes.most_common(1)[0][0]


class DiscoveryAgent(Agent):
    agent_id = "AG-02"
    name = "Discovery & Cataloging"
    authority = Authority.AUTO_ACT

    def scan(self, directory: Path) -> list[DatasetEntry]:
        entries = []
        for path in sorted(Path(directory).glob("*.csv")):
            entry = self._scan_file(path)
            self.catalog.upsert_dataset(entry)
            entries.append(entry)
            self.bus.publish("dataset.discovered", {"dataset": entry.name})
        return entries

    def _scan_file(self, path: Path) -> DatasetEntry:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        columns = []
        for field_name in rows[0].keys() if rows else []:
            values = [row.get(field_name, "") or "" for row in rows]
            columns.append(
                DatasetColumn(
                    name=field_name,
                    inferred_type=infer_column_type(values),
                    null_count=sum(1 for v in values if v == ""),
                    sample_values=[v for v in values if v != ""][:5],
                )
            )

        return DatasetEntry(
            name=path.stem,
            source_path=str(path),
            row_count=len(rows),
            columns=columns,
            discovered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
