"""AG-10 · Retention & Lifecycle.

Derives each dataset's age from its newest date column, compares that
against the schedule for its retention class, and flags what is past
due. Legal holds are enforced auto-act and always win: a dataset under
hold is never proposed for disposal, even when its schedule has expired.

Disposal itself is only ever recommended — deletion is irreversible, so
the Data Owner makes that call.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import RetentionFinding
from governance.sources import read_rows


class RetentionAgent(Agent):
    agent_id = "AG-10"
    name = "Retention & Lifecycle"
    authority = Authority.RECOMMEND

    def __init__(self, bus, catalog, schedules: dict | None = None, legal_holds=None) -> None:
        super().__init__(bus, catalog)
        self.schedules = schedules or {}
        self.legal_holds = set(legal_holds or [])

    @staticmethod
    def load_config(path: str | Path) -> tuple[dict, list[str]]:
        config = json.loads(Path(path).read_text())
        return config["schedules"], config.get("legal_holds", [])

    def evaluate(self, as_of: date | None = None) -> list[RetentionFinding]:
        as_of = as_of or date.today()
        findings = []

        for entry in self.catalog.all_datasets():
            retention_class = entry.retention_class or "unclassified"
            schedule = self.schedules.get(retention_class)
            if schedule is None:
                continue

            newest = self._newest_date(entry)
            if newest is None:
                continue

            retain_until = date(
                newest.year + schedule["retention_years"], newest.month, newest.day
            )

            if entry.name in self.legal_holds:
                finding = RetentionFinding(
                    dataset=entry.name,
                    retention_class=retention_class,
                    retain_until=retain_until.isoformat(),
                    status="legal_hold",
                    detail=f"{entry.name} is under legal hold; disposition is blocked regardless of schedule.",
                )
            elif retain_until <= as_of:
                finding = RetentionFinding(
                    dataset=entry.name,
                    retention_class=retention_class,
                    retain_until=retain_until.isoformat(),
                    status="due_for_disposition",
                    detail=(
                        f"{entry.name} ({retention_class}, {schedule['retention_years']}y) "
                        f"passed its retention date on {retain_until.isoformat()}; "
                        f"owner sign-off required before disposal."
                    ),
                )
            else:
                finding = RetentionFinding(
                    dataset=entry.name,
                    retention_class=retention_class,
                    retain_until=retain_until.isoformat(),
                    status="within_schedule",
                    detail=f"{entry.name} is retained until {retain_until.isoformat()}.",
                )

            self.catalog.record("retention_findings", finding)
            findings.append(finding)

            if finding.status == "due_for_disposition":
                self.bus.publish(
                    "retention.due", {"dataset": entry.name, "detail": finding.detail}
                )

        return findings

    def _newest_date(self, entry) -> date | None:
        date_columns = [c.name for c in entry.columns if c.inferred_type == "date"]
        if not date_columns:
            return None

        newest = None
        for row in read_rows(entry.source_path):
            for column_name in date_columns:
                value = row.get(column_name, "")
                if not value:
                    continue
                try:
                    parsed = date.fromisoformat(value)
                except ValueError:
                    continue
                if newest is None or parsed > newest:
                    newest = parsed
        return newest
