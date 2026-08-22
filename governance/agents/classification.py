"""AG-03 · Classification & Sensitivity.

Reacts to dataset.discovered: scans column names and sample values for
PII, labels sensitivity in the catalog, and — when PII shows up in a
column policy didn't approve for it — publishes classification.exception
instead of quietly labeling it. That's the escalate branch; everywhere
else this agent auto-acts.
"""

from __future__ import annotations

import re

from governance.agents.base import Agent, Authority

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_RE = re.compile(r"\b\d{3}[-.]\d{3}[-.]\d{4}\b")

NAME_HINTS = {
    "email": "email",
    "phone": "phone",
    "ssn": "ssn",
    "full_name": "name",
}

# dataset -> columns where policy has already approved PII to live.
# Anything detected outside this map is treated as an exception.
DEFAULT_APPROVED_ZONES: dict[str, set[str]] = {
    "customers": {"full_name", "email", "phone", "ssn"},
    "orders": set(),
    "products": set(),
}


def detect_kinds(column_name: str, sample_values: list[str]) -> set[str]:
    kinds: set[str] = set()
    blob = " ".join(sample_values)
    if EMAIL_RE.search(blob):
        kinds.add("email")
    if SSN_RE.search(blob):
        kinds.add("ssn")
    if PHONE_RE.search(blob):
        kinds.add("phone")

    lowered = column_name.lower()
    for hint, kind in NAME_HINTS.items():
        if hint in lowered:
            kinds.add(kind)
    return kinds


class ClassificationAgent(Agent):
    agent_id = "AG-03"
    name = "Classification & Sensitivity"
    authority = Authority.RECOMMEND

    def __init__(self, bus, catalog, approved_zones: dict[str, set[str]] | None = None) -> None:
        super().__init__(bus, catalog)
        self.approved_zones = approved_zones or DEFAULT_APPROVED_ZONES

    def handle_dataset_discovered(self, payload: dict) -> None:
        dataset_name = payload["dataset"]
        entry = self.catalog.datasets[dataset_name]
        approved = self.approved_zones.get(dataset_name, set())

        for column in entry.columns:
            kinds = detect_kinds(column.name, column.sample_values)
            if not kinds:
                self.catalog.update_column(dataset_name, column.name, sensitivity="general")
                continue

            self.catalog.update_column(
                dataset_name,
                column.name,
                sensitivity="restricted",
                regulatory_tags=sorted(kinds),
            )

            if column.name not in approved:
                self.bus.publish(
                    "classification.exception",
                    {
                        "dataset": dataset_name,
                        "column": column.name,
                        "kinds": sorted(kinds),
                        "sample": column.sample_values[:2],
                    },
                )
