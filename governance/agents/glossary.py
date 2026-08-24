"""AG-06 · Metadata & Glossary.

Links technical columns to business terms, drafts definitions for the
ones nothing matches, and flags terms whose linked columns disagree with
each other. Authority is recommend, so every link this agent writes
lands as `term_status="draft"` until a steward approves it — nothing
here is presented to consumers as settled.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.agents.classification import detect_kinds

ARTICLE_WORDS = {"id", "sku", "url", "ssn"}


class GlossaryAgent(Agent):
    agent_id = "AG-06"
    name = "Metadata & Glossary"
    authority = Authority.RECOMMEND

    def __init__(self, bus, catalog, terms: list[dict] | None = None) -> None:
        super().__init__(bus, catalog)
        self.terms = terms or []
        self.drafted: list[dict] = []
        self.conflicts: list[dict] = []

    @staticmethod
    def load_terms(path: str | Path) -> list[dict]:
        return json.loads(Path(path).read_text())["terms"]

    def handle_dataset_discovered(self, payload: dict) -> None:
        self.link(payload["dataset"])

    def link(self, dataset_name: str) -> None:
        entry = self.catalog.datasets[dataset_name]
        for column in entry.columns:
            term = self._match(column.name)
            if term:
                self.catalog.update_column(
                    dataset_name, column.name, glossary_term=term["term"], term_status="draft"
                )
            else:
                draft = self._draft_definition(dataset_name, column)
                self.drafted.append(draft)
                self.bus.publish("glossary.draft", draft)

    def detect_conflicts(self) -> list[dict]:
        """A term linked to columns of disagreeing types is a real modeling
        problem, not a naming quibble — surface it for the steward."""
        by_term: dict[str, list[tuple[str, str, str]]] = {}
        for dataset, column in self.catalog.all_columns():
            if column.glossary_term:
                by_term.setdefault(column.glossary_term, []).append(
                    (dataset.name, column.name, column.inferred_type)
                )

        self.conflicts = []
        for term, members in sorted(by_term.items()):
            types = {t for _, _, t in members}
            if len(types) > 1:
                conflict = {
                    "term": term,
                    "types": sorted(types),
                    "members": [f"{d}.{c} ({t})" for d, c, t in members],
                }
                self.conflicts.append(conflict)
                self.bus.publish("glossary.conflict", conflict)
        return self.conflicts

    # -- matching ----------------------------------------------------------

    def _match(self, column_name: str) -> dict | None:
        needle = column_name.lower()
        for term in self.terms:
            if needle == term["term"].lower().replace(" ", "_"):
                return term
            if needle in [s.lower() for s in term.get("synonyms", [])]:
                return term
        return None

    @staticmethod
    def _draft_definition(dataset_name: str, column) -> dict:
        words = [
            w.upper() if w in ARTICLE_WORDS else w
            for w in column_name_words(column.name)
        ]
        phrase = " ".join(words)

        # Never illustrate a definition with values from a column that holds
        # sensitive data — a glossary is published to consumers, so a helpful
        # "e.g." would republish the PII this system exists to contain.
        # Checked two ways so this holds regardless of whether AG-03 has
        # labeled the column yet.
        withheld = column.sensitivity == "restricted" or bool(
            detect_kinds(column.name, column.sample_values)
        )
        samples = "" if withheld else ", ".join(column.sample_values[:3])

        definition = (
            f"The {phrase} recorded on each {dataset_name.rstrip('s')} record "
            f"(type: {column.inferred_type}"
            + (f"; e.g. {samples}" if samples else "")
            + (
                "; examples withheld — column holds sensitive data"
                if withheld
                else ""
            )
            + ")."
        )
        return {
            "dataset": dataset_name,
            "column": column.name,
            "proposed_term": phrase.title(),
            "proposed_definition": definition,
            "status": "awaiting_steward_review",
        }


def column_name_words(name: str) -> list[str]:
    return [w for w in name.replace("-", "_").split("_") if w]
