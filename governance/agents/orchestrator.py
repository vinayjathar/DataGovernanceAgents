"""AG-01 · Orchestrator (Governance Conductor).

Wires the event bus and the agents together and exposes one entrypoint
per rollout phase. It does not make governance decisions itself — it
routes events between the agents that do.
"""

from __future__ import annotations

from pathlib import Path

from governance.agents.classification import ClassificationAgent
from governance.agents.discovery import DiscoveryAgent
from governance.agents.issue import IssueAgent
from governance.catalog import Catalog
from governance.events import EventBus


class Orchestrator:
    agent_id = "AG-01"
    name = "Governance Conductor"

    def __init__(self, catalog: Catalog) -> None:
        self.bus = EventBus()
        self.catalog = catalog

        self.discovery = DiscoveryAgent(self.bus, catalog)
        self.classification = ClassificationAgent(self.bus, catalog)
        self.issue = IssueAgent(self.bus, catalog)

        self.bus.subscribe("dataset.discovered", self.classification.handle_dataset_discovered)
        self.bus.subscribe("classification.exception", self.issue.handle_exception)

    def run_phase0(self, data_dir: Path) -> None:
        """Foundation phase: stand up the catalog and first sensitivity labels."""
        self.discovery.scan(data_dir)
