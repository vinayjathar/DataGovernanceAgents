"""AG-05 · Lineage & Impact Analysis.

Builds the pipeline graph and — the part that earns its keep —
propagates sensitivity downstream. A derived dataset built from a
restricted column is itself restricted, whether or not anyone
remembered to label it. Without this, classification stops at the
source and every downstream table looks clean.

AG-13 and AG-14 both query this graph rather than re-deriving it.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance.agents.base import Agent, Authority
from governance.catalog import LineageEdge, LineageNode

SENSITIVITY_RANK = {"general": 0, "unclassified": 0, "restricted": 2}


class LineageAgent(Agent):
    agent_id = "AG-05"
    name = "Lineage & Impact Analysis"
    authority = Authority.AUTO_ACT

    @staticmethod
    def load_pipelines(path: str | Path) -> list[dict]:
        return json.loads(Path(path).read_text())["pipelines"]

    def build(self, pipelines: list[dict]) -> None:
        for name in self.catalog.datasets:
            self.catalog.upsert_lineage_node(LineageNode(name=name, kind="source"))

        for pipeline in pipelines:
            output = pipeline["output"]
            if output not in self.catalog.lineage_nodes:
                self.catalog.upsert_lineage_node(LineageNode(name=output, kind="derived"))

            for source in pipeline["inputs"]:
                if source not in self.catalog.lineage_nodes:
                    self.catalog.upsert_lineage_node(LineageNode(name=source, kind="derived"))
                self.catalog.record(
                    "lineage_edges",
                    LineageEdge(
                        pipeline=pipeline["name"],
                        source=source,
                        target=output,
                        consumed_columns=pipeline.get("consumes_columns", {}).get(source, []),
                    ),
                )

        self._propagate_sensitivity()
        self.bus.publish(
            "lineage.built",
            {"nodes": len(self.catalog.lineage_nodes), "edges": len(self.catalog.lineage_edges)},
        )

    def _propagate_sensitivity(self) -> None:
        """Seed every source node from its catalog entry, then push
        downstream until nothing changes."""
        for name, node in self.catalog.lineage_nodes.items():
            entry = self.catalog.datasets.get(name)
            if entry is None:
                continue
            restricted = [c for c in entry.columns if c.sensitivity == "restricted"]
            if restricted:
                node.inherited_sensitivity = "restricted"
                node.inherited_tags = sorted({t for c in restricted for t in c.regulatory_tags})

        changed = True
        while changed:
            changed = False
            for edge in self.catalog.lineage_edges:
                upstream = self.catalog.lineage_nodes[edge.source]
                downstream = self.catalog.lineage_nodes[edge.target]
                if SENSITIVITY_RANK.get(upstream.inherited_sensitivity, 0) > SENSITIVITY_RANK.get(
                    downstream.inherited_sensitivity, 0
                ):
                    downstream.inherited_sensitivity = upstream.inherited_sensitivity
                    changed = True
                merged = sorted(set(downstream.inherited_tags) | set(upstream.inherited_tags))
                if merged != downstream.inherited_tags:
                    downstream.inherited_tags = merged
                    changed = True
        self.catalog._persist()

    # -- impact analysis ---------------------------------------------------

    def impact_of(self, dataset: str) -> list[str]:
        return self.catalog.downstream_of(dataset)

    def column_consumers(self, dataset: str, column: str) -> list[str]:
        return self.catalog.consumers_of_column(dataset, column)
