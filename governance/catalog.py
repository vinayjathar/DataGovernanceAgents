"""The shared substrate every agent reads and writes.

A tiny stand-in for the "Data Catalog / Knowledge Graph" box in the
architecture diagram — in a real deployment this would be a proper
catalog service; here it's a JSON-backed store so the whole pipeline
runs with zero external dependencies.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class DatasetColumn:
    name: str
    inferred_type: str
    null_count: int
    sample_values: list[str] = field(default_factory=list)
    sensitivity: str = "unclassified"
    regulatory_tags: list[str] = field(default_factory=list)


@dataclass
class DatasetEntry:
    name: str
    source_path: str
    row_count: int
    columns: list[DatasetColumn]
    discovered_at: str
    status: str = "cataloged"


@dataclass
class Issue:
    id: str
    dataset: str
    column: str
    kind: str
    detail: str
    assigned_to: str
    status: str
    opened_at: str
    sla_hours: int


class Catalog:
    """In-memory catalog, persisted to a JSON file after every write."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path
        self.datasets: dict[str, DatasetEntry] = {}
        self.issues: list[Issue] = []

    def upsert_dataset(self, entry: DatasetEntry) -> None:
        self.datasets[entry.name] = entry
        self._persist()

    def update_column(self, dataset_name: str, column_name: str, **fields) -> None:
        dataset = self.datasets[dataset_name]
        for column in dataset.columns:
            if column.name == column_name:
                for key, value in fields.items():
                    setattr(column, key, value)
                break
        self._persist()

    def add_issue(self, issue: Issue) -> None:
        self.issues.append(issue)
        self._persist()

    def all_datasets(self) -> list[DatasetEntry]:
        return list(self.datasets.values())

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.status == "open"]

    def _persist(self) -> None:
        if self.persist_path is None:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "datasets": {name: asdict(entry) for name, entry in self.datasets.items()},
            "issues": [asdict(issue) for issue in self.issues],
        }
        self.persist_path.write_text(json.dumps(snapshot, indent=2))
