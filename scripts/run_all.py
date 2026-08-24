#!/usr/bin/env python3
"""Run every phase end to end against the mock dataset.

Usage:
    python3 scripts/run_all.py
    python3 scripts/run_all.py --as-of 2026-08-22
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from governance.agents.orchestrator import Orchestrator  # noqa: E402
from governance.catalog import Catalog  # noqa: E402


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=REPO_ROOT / "mock_data", type=Path)
    parser.add_argument("--config", default=REPO_ROOT / "config", type=Path)
    parser.add_argument("--out", default=REPO_ROOT / "output" / "catalog_full.json", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    catalog = Catalog(persist_path=args.out)
    orchestrator = Orchestrator(catalog, config_dir=args.config)
    scorecard = orchestrator.run_all(args.data, as_of=args.as_of)

    report(orchestrator, catalog, scorecard)
    print(f"\nFull catalog snapshot written to {args.out}")


def report(orchestrator, catalog: Catalog, scorecard: dict) -> None:
    rule("AG-02 DISCOVERY / AG-03 CLASSIFICATION — catalog")
    for dataset in catalog.all_datasets():
        owner = dataset.owner or "UNOWNED"
        print(f"\n[{dataset.name}]  {dataset.row_count} rows  owner={owner}  class={dataset.retention_class}")
        for column in dataset.columns:
            tags = f" tags={column.regulatory_tags}" if column.regulatory_tags else ""
            term = f" term='{column.glossary_term}'" if column.glossary_term else ""
            print(f"    {column.name:<20} {column.inferred_type:<8} {column.sensitivity:<12}{tags}{term}")

    rule("AG-04 DATA QUALITY — failed checks")
    failures = [q for q in catalog.quality_results if not q.passed]
    print(f"{len(catalog.quality_results)} checks run, {len(failures)} failed\n")
    for result in failures:
        print(f"  [{result.dimension:<12}] {result.detail}  (score {result.score})")

    rule("AG-06 METADATA & GLOSSARY")
    linked = [c for _, c in catalog.all_columns() if c.glossary_term]
    print(f"{len(linked)} columns linked to terms, {len(orchestrator.glossary.drafted)} definitions drafted\n")
    for conflict in orchestrator.glossary.conflicts:
        print(f"  CONFLICT  '{conflict['term']}' has disagreeing types {conflict['types']}")
        for member in conflict["members"]:
            print(f"            - {member}")
    for draft in orchestrator.glossary.drafted[:4]:
        print(f"  DRAFT     {draft['dataset']}.{draft['column']} -> \"{draft['proposed_definition']}\"")

    rule("AG-05 LINEAGE — sensitivity propagation")
    for name, node in catalog.lineage_nodes.items():
        marker = "*" if node.kind == "derived" else " "
        tags = f" tags={node.inherited_tags}" if node.inherited_tags else ""
        print(f"  {marker} {name:<20} {node.kind:<9} {node.inherited_sensitivity:<12}{tags}")
    print("\n  (* derived — sensitivity inherited through the pipeline graph, not labeled at source)")

    rule("AG-09 MDM — proposed golden records")
    for record in catalog.golden_records:
        print(
            f"  {record.id}  rule={record.match_rule:<24} conf={record.confidence}  "
            f"members={record.members}"
        )
        print(f"          survived: {record.attributes}")

    rule("AG-10 RETENTION")
    for finding in catalog.retention_findings:
        print(f"  [{finding.status:<21}] {finding.detail}")

    rule("AG-08 ACCESS & ENTITLEMENT")
    for decision in catalog.access_decisions:
        print(f"  {decision.request_id}  {decision.decision:<14} risk={decision.risk:<9} by={decision.decided_by}")
        print(f"           {decision.rationale}")

    rule("AG-07 POLICY & COMPLIANCE")
    print(f"rule compliance rate: {orchestrator.policy.compliance_rate() * 100:.0f}%\n")
    for finding in catalog.policy_findings:
        print(f"  [{finding.severity:<6}] {finding.rule_id}  {finding.dataset}.{finding.column}")
        print(f"           {finding.detail}")
        print(f"           basis: {finding.regulation}")

    rule("AG-13 RISK & AI-GOVERNANCE")
    for assessment in sorted(catalog.risk_assessments, key=lambda a: -a.score):
        print(f"  {assessment.subject:<20} score={assessment.score:<4} band={assessment.band}")
        print(f"           drivers: {'; '.join(assessment.drivers)}")
    print()
    for decision in catalog.training_decisions:
        print(f"  {decision.model:<26} {decision.decision}")
        print(f"           {decision.rationale}")

    rule("AG-14 DEVELOPER GUARDRAIL — pre-merge check")
    for finding in catalog.guardrail_findings:
        print(f"  [{finding.verdict.upper():<5}] {finding.op} {finding.target}")
        print(f"           {finding.detail}")

    rule("AG-11 ISSUE & REMEDIATION — open tickets")
    for issue in catalog.open_issues():
        target = f"{issue.dataset}.{issue.column}"
        print(
            f"  {issue.id}  [{issue.severity:<6}] {target:<34} "
            f"{issue.raised_by} -> {issue.assigned_to:<28} sla={issue.sla_hours}h"
        )

    rule("AG-12 AUDIT & MONITORING — governance scorecard")
    coverage = scorecard["coverage"]
    print(f"  datasets cataloged     {coverage['datasets_cataloged']}")
    print(f"  ownership assigned     {coverage['ownership_assigned']}%")
    print(f"  columns classified     {coverage['columns_classified']}%")
    print(f"  glossary linked        {coverage['glossary_linked']}%")
    print(f"  quality pass rate      {scorecard['quality']['pass_rate']}%  ({scorecard['quality']['checks_run']} checks)")
    print(f"  rule compliance        {scorecard['compliance']['rule_compliance_rate'] * 100:.0f}%")
    print(f"  policy findings        {scorecard['compliance']['policy_findings']}  {scorecard['compliance']['findings_by_severity']}")
    print(f"  open issues            {scorecard['issues']['open']}  {scorecard['issues']['by_severity']}")
    print(f"  raised by              {scorecard['issues']['by_raising_agent']}")
    print(f"  high-risk datasets     {scorecard['risk']['high_risk_datasets']}")
    print(f"  audit trail events     {scorecard['audit_trail_events']}")


if __name__ == "__main__":
    main()
