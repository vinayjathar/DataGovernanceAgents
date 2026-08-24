"""AG-09 · MDM & Reference Data.

Resolves customer records scattered across systems into golden records.
Two match rules, tried strongest first: normalized email is an identity
claim; phone plus a close name is a strong but weaker signal used when
email is missing on one side.

Authority is recommend — every golden record lands as `proposed`.
Auto-merging identities is exactly the kind of irreversible call that
belongs with the Data Owner, so this agent proposes and stops.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from governance.agents.base import Agent, Authority
from governance.catalog import GoldenRecord
from governance.sources import read_rows

NAME_SIMILARITY_THRESHOLD = 0.82

# source dataset -> the column names that carry each canonical attribute
FIELD_MAP = {
    "customers": {"id": "customer_id", "name": "full_name", "email": "email", "phone": "phone"},
    "legacy_customers": {
        "id": "cust_id",
        "name": "full_name",
        "email": "email_address",
        "phone": "contact_phone",
    },
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


class MDMAgent(Agent):
    agent_id = "AG-09"
    name = "MDM & Reference Data"
    authority = Authority.RECOMMEND

    def resolve(self, dataset_names: list[str]) -> list[GoldenRecord]:
        records = self._collect(dataset_names)
        clusters = self._cluster(records)

        golden = []
        for index, (rule, confidence, members) in enumerate(clusters, start=1):
            record = GoldenRecord(
                id=f"GR-{index:03d}",
                match_rule=rule,
                confidence=confidence,
                members=[m["ref"] for m in members],
                attributes=self._survive(members),
            )
            self.catalog.record("golden_records", record)
            golden.append(record)

        self.bus.publish(
            "mdm.records_proposed",
            {"proposed": len(golden), "sources": dataset_names},
        )
        return golden

    # -- collection --------------------------------------------------------

    def _collect(self, dataset_names: list[str]) -> list[dict]:
        collected = []
        for dataset_name in dataset_names:
            entry = self.catalog.datasets.get(dataset_name)
            fields = FIELD_MAP.get(dataset_name)
            if entry is None or fields is None:
                continue
            for row in read_rows(entry.source_path):
                collected.append(
                    {
                        "ref": f"{dataset_name}:{row.get(fields['id'], '')}",
                        "source": dataset_name,
                        "id": row.get(fields["id"], ""),
                        "name": row.get(fields["name"], ""),
                        "email": row.get(fields["email"], ""),
                        "phone": row.get(fields["phone"], ""),
                    }
                )
        return collected

    # -- matching ----------------------------------------------------------

    def _cluster(self, records: list[dict]) -> list[tuple[str, float, list[dict]]]:
        unassigned = list(records)
        clusters: list[tuple[str, float, list[dict]]] = []

        while unassigned:
            seed = unassigned.pop(0)
            members = [seed]
            rule, confidence = "singleton", 1.0

            for candidate in list(unassigned):
                matched_rule, matched_confidence = self._match(seed, candidate)
                if matched_rule:
                    members.append(candidate)
                    unassigned.remove(candidate)
                    rule, confidence = matched_rule, matched_confidence

            clusters.append((rule, confidence, members))
        return clusters

    @staticmethod
    def _match(a: dict, b: dict) -> tuple[str | None, float]:
        if a["email"] and b["email"] and normalize_email(a["email"]) == normalize_email(b["email"]):
            return "exact_email", 0.99

        phone_a, phone_b = normalize_phone(a["phone"]), normalize_phone(b["phone"])
        if phone_a and phone_a == phone_b:
            similarity = name_similarity(a["name"], b["name"])
            if similarity >= NAME_SIMILARITY_THRESHOLD:
                return "phone_and_similar_name", round(0.75 + (similarity - 0.82) * 0.5, 3)

        return None, 0.0

    # -- survivorship ------------------------------------------------------

    @staticmethod
    def _survive(members: list[dict]) -> dict[str, str]:
        """Most-complete-value wins, with the modern system breaking ties."""
        ordered = sorted(members, key=lambda m: 0 if m["source"] == "customers" else 1)
        attributes = {}
        for field_name in ("name", "email", "phone"):
            attributes[field_name] = next(
                (m[field_name] for m in ordered if m[field_name]), ""
            )
        attributes["source_count"] = str(len({m["source"] for m in members}))
        return attributes
