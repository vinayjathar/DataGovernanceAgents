"""The shared substrate every agent reads and writes.

A tiny stand-in for the "Data Catalog / Knowledge Graph" box in the
architecture diagram — in a real deployment this would be a proper
catalog service; here it's a JSON-backed store so the whole pipeline
runs with zero external dependencies.

Every agent's output lands in one of the collections on `Catalog`, which
is what lets a later agent build on an earlier one's work without the
two of them knowing about each other.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------
# Catalog records
# --------------------------------------------------------------------------


@dataclass
class DatasetColumn:
    name: str
    inferred_type: str
    null_count: int
    sample_values: list[str] = field(default_factory=list)
    sensitivity: str = "unclassified"
    regulatory_tags: list[str] = field(default_factory=list)
    glossary_term: str | None = None
    term_status: str | None = None


@dataclass
class DatasetEntry:
    name: str
    source_path: str
    row_count: int
    columns: list[DatasetColumn]
    discovered_at: str
    status: str = "cataloged"
    owner: str | None = None
    domain: str | None = None
    retention_class: str | None = None

    def column(self, name: str) -> DatasetColumn | None:
        return next((c for c in self.columns if c.name == name), None)

    def has_restricted_column(self) -> bool:
        return any(c.sensitivity == "restricted" for c in self.columns)


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
    severity: str = "medium"
    raised_by: str = "AG-03"


@dataclass
class QualityResult:
    dataset: str
    column: str
    dimension: str
    passed: bool
    detail: str
    score: float


@dataclass
class PolicyFinding:
    rule_id: str
    title: str
    regulation: str
    severity: str
    dataset: str
    column: str
    detail: str


@dataclass
class LineageNode:
    name: str
    kind: str  # "source" | "derived"
    inherited_sensitivity: str = "general"
    inherited_tags: list[str] = field(default_factory=list)


@dataclass
class LineageEdge:
    pipeline: str
    source: str
    target: str
    consumed_columns: list[str] = field(default_factory=list)


@dataclass
class GoldenRecord:
    id: str
    match_rule: str
    confidence: float
    members: list[str]
    attributes: dict[str, str]
    status: str = "proposed"


@dataclass
class AccessDecision:
    request_id: str
    requester: str
    dataset: str
    purpose: str
    decision: str  # "auto-approved" | "escalated" | "denied"
    risk: str
    rationale: str
    decided_by: str


@dataclass
class RetentionFinding:
    dataset: str
    retention_class: str
    retain_until: str
    status: str  # "within_schedule" | "due_for_disposition" | "legal_hold"
    detail: str


@dataclass
class RiskAssessment:
    subject: str
    score: int
    band: str  # "low" | "moderate" | "high"
    drivers: list[str]


@dataclass
class TrainingDecision:
    model: str
    decision: str  # "approved" | "approved_with_masking" | "blocked"
    blocking_columns: list[str]
    rationale: str


@dataclass
class GuardrailFinding:
    pull_request: str
    op: str
    target: str
    verdict: str  # "block" | "warn" | "pass"
    detail: str


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------


class Catalog:
    """In-memory catalog, persisted to a JSON file after every write."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path
        self.datasets: dict[str, DatasetEntry] = {}
        self.issues: list[Issue] = []
        self.quality_results: list[QualityResult] = []
        self.policy_findings: list[PolicyFinding] = []
        self.lineage_nodes: dict[str, LineageNode] = {}
        self.lineage_edges: list[LineageEdge] = []
        self.golden_records: list[GoldenRecord] = []
        self.access_decisions: list[AccessDecision] = []
        self.retention_findings: list[RetentionFinding] = []
        self.risk_assessments: list[RiskAssessment] = []
        self.training_decisions: list[TrainingDecision] = []
        self.guardrail_findings: list[GuardrailFinding] = []
        self.scorecard: dict[str, object] = {}

    # -- writes ------------------------------------------------------------

    def upsert_dataset(self, entry: DatasetEntry) -> None:
        self.datasets[entry.name] = entry
        self._persist()

    def update_dataset(self, dataset_name: str, **fields) -> None:
        dataset = self.datasets[dataset_name]
        for key, value in fields.items():
            setattr(dataset, key, value)
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

    def record(self, collection: str, item) -> None:
        """Append to any of the agent-output collections by name."""
        getattr(self, collection).append(item)
        self._persist()

    def upsert_lineage_node(self, node: LineageNode) -> None:
        self.lineage_nodes[node.name] = node
        self._persist()

    def set_scorecard(self, scorecard: dict) -> None:
        self.scorecard = scorecard
        self._persist()

    # -- reads -------------------------------------------------------------

    def all_datasets(self) -> list[DatasetEntry]:
        return list(self.datasets.values())

    def all_columns(self):
        for dataset in self.datasets.values():
            for column in dataset.columns:
                yield dataset, column

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.status == "open"]

    def downstream_of(self, dataset: str) -> list[str]:
        """Transitive downstream closure — what AG-14 and AG-13 ask lineage for."""
        seen: list[str] = []
        frontier = [dataset]
        while frontier:
            current = frontier.pop()
            for edge in self.lineage_edges:
                if edge.source == current and edge.target not in seen:
                    seen.append(edge.target)
                    frontier.append(edge.target)
        return seen

    def consumers_of_column(self, dataset: str, column: str) -> list[str]:
        return [
            edge.target
            for edge in self.lineage_edges
            if edge.source == dataset and column in edge.consumed_columns
        ]

    # -- persistence -------------------------------------------------------

    def _persist(self) -> None:
        if self.persist_path is None:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "datasets": {name: asdict(e) for name, e in self.datasets.items()},
            "issues": [asdict(i) for i in self.issues],
            "quality_results": [asdict(q) for q in self.quality_results],
            "policy_findings": [asdict(p) for p in self.policy_findings],
            "lineage_nodes": {n: asdict(v) for n, v in self.lineage_nodes.items()},
            "lineage_edges": [asdict(e) for e in self.lineage_edges],
            "golden_records": [asdict(g) for g in self.golden_records],
            "access_decisions": [asdict(a) for a in self.access_decisions],
            "retention_findings": [asdict(r) for r in self.retention_findings],
            "risk_assessments": [asdict(r) for r in self.risk_assessments],
            "training_decisions": [asdict(t) for t in self.training_decisions],
            "guardrail_findings": [asdict(g) for g in self.guardrail_findings],
            "scorecard": self.scorecard,
        }
        self.persist_path.write_text(json.dumps(snapshot, indent=2))
