"""AG-01 · Orchestrator (Governance Conductor).

Wires the event bus and the agents together and exposes one entrypoint
per rollout phase. It does not make governance decisions itself — it
routes events between the agents that do, and fixes the order a pass
runs in.

Phases are cumulative and wired lazily, which is what lets `run_phase0`
still behave exactly as it did before Phase 1 existed: agents from a
phase you have not rolled out are constructed but never subscribed, so
they cannot act.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from governance.agents.access import AccessAgent
from governance.agents.audit import AuditAgent
from governance.agents.classification import ClassificationAgent
from governance.agents.discovery import DiscoveryAgent
from governance.agents.glossary import GlossaryAgent
from governance.agents.guardrail import GuardrailAgent
from governance.agents.issue import IssueAgent
from governance.agents.lineage import LineageAgent
from governance.agents.mdm import MDMAgent
from governance.agents.policy import PolicyAgent
from governance.agents.quality import QualityAgent
from governance.agents.retention import RetentionAgent
from governance.agents.risk import RiskAgent
from governance.catalog import Catalog
from governance.events import EventBus
from governance.policy_engine import PolicyEngine

MDM_SOURCES = ["customers", "legacy_customers"]


class Orchestrator:
    agent_id = "AG-01"
    name = "Governance Conductor"

    def __init__(self, catalog: Catalog, config_dir: Path | None = None) -> None:
        self.bus = EventBus()
        self.catalog = catalog
        self.config_dir = Path(config_dir) if config_dir else None
        self._wired: set[int] = set()

        # Phase 0 — Foundation
        self.discovery = DiscoveryAgent(self.bus, catalog)
        self.issue = IssueAgent(self.bus, catalog)

        if self.config_dir is None:
            self.policy_engine = None
            self.classification = ClassificationAgent(self.bus, catalog)
        else:
            self.policy_engine = PolicyEngine.from_file(self.config_dir / "policy_rules.json")
            self.classification = ClassificationAgent(
                self.bus, catalog, policy_engine=self.policy_engine
            )
            self._build_later_phases()

        self._wire_phase(0)

    # -- construction ------------------------------------------------------

    def _build_later_phases(self) -> None:
        cfg = self.config_dir

        # Phase 1 — Core Controls
        self.quality = QualityAgent(self.bus, self.catalog, QualityAgent.load_rules(cfg / "quality_rules.json"))
        self.glossary = GlossaryAgent(self.bus, self.catalog, GlossaryAgent.load_terms(cfg / "glossary.json"))
        self.policy = PolicyAgent(self.bus, self.catalog, self.policy_engine)
        self.access = AccessAgent(self.bus, self.catalog)

        # Phase 2 — Full Operations
        self.lineage = LineageAgent(self.bus, self.catalog)
        self.mdm = MDMAgent(self.bus, self.catalog)
        schedules, holds = RetentionAgent.load_config(cfg / "retention_schedules.json")
        self.retention = RetentionAgent(self.bus, self.catalog, schedules, holds)
        self.risk = RiskAgent(self.bus, self.catalog)
        self.guardrail = GuardrailAgent(self.bus, self.catalog, self.policy_engine)

        # Phase 3 — Continuous Governance
        self.audit = AuditAgent(self.bus, self.catalog)

    # -- wiring ------------------------------------------------------------

    def _wire_phase(self, phase: int) -> None:
        if phase in self._wired:
            return
        self._wired.add(phase)

        if phase == 0:
            self.bus.subscribe("dataset.discovered", self.classification.handle_dataset_discovered)
            self.bus.subscribe("classification.exception", self.issue.handle_exception)

        elif phase == 1:
            self.bus.subscribe("dataset.discovered", self.quality.handle_dataset_discovered)
            self.bus.subscribe("dataset.discovered", self.glossary.handle_dataset_discovered)
            self.bus.subscribe("quality.violation", self.issue.handle_quality_violation)
            self.bus.subscribe("policy.violation", self.issue.handle_policy_violation)
            self.bus.subscribe("access.escalated", self.issue.handle_access_escalated)

        elif phase == 2:
            self.bus.subscribe("retention.due", self.issue.handle_retention_due)
            self.bus.subscribe("training.blocked", self.issue.handle_training_blocked)

        elif phase == 3:
            self.bus.subscribe_all(self.audit.observe)

    def _require_config(self) -> None:
        if self.config_dir is None:
            raise RuntimeError(
                "Phases 1+ need a config directory: Orchestrator(catalog, config_dir=...)"
            )

    # -- phase entrypoints -------------------------------------------------

    def run_phase0(self, data_dir: Path) -> None:
        """Foundation: stand up the catalog and first sensitivity labels."""
        self.discovery.scan(data_dir)

    def run_all(self, data_dir: Path, as_of: date | None = None) -> dict:
        """Every phase rolled out, in dependency order.

        Ordering is load-bearing: each agent asserts over what the ones
        before it wrote. Policy runs after glossary and ownership because
        two of its rules check exactly those; risk runs after lineage and
        access because its score reads both.
        """
        self._require_config()
        for phase in (1, 2, 3):
            self._wire_phase(phase)

        cfg = self.config_dir

        # AG-02 -> fans out to AG-03 classify, AG-04 profile, AG-06 link
        self.discovery.scan(data_dir)
        self.glossary.detect_conflicts()

        # Ownership must land before the rules that assert on it
        self.policy.apply_owner_registry(PolicyAgent.load_owners(cfg / "data_owners.json"))

        self.lineage.build(LineageAgent.load_pipelines(cfg / "pipelines.json"))
        self.mdm.resolve(MDM_SOURCES)
        self.retention.evaluate(as_of=as_of)
        self.access.process(AccessAgent.load_requests(cfg / "access_requests.json"))

        self.policy.evaluate_catalog()

        self.risk.assess_all()
        self.risk.review_training(RiskAgent.load_manifests(cfg / "training_manifests.json"))
        self.guardrail.check(GuardrailAgent.load_change(cfg / "schema_change.json"))

        return self.audit.build_scorecard(compliance_rate=self.policy.compliance_rate())
