#!/usr/bin/env python3
"""Run Phase 0 (Foundation) end to end against the mock dataset.

Usage:
    python3 scripts/run_phase0.py
    python3 scripts/run_phase0.py --data mock_data --out output/catalog.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from governance.agents.orchestrator import Orchestrator  # noqa: E402
from governance.catalog import Catalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=REPO_ROOT / "mock_data", type=Path)
    parser.add_argument("--out", default=REPO_ROOT / "output" / "catalog.json", type=Path)
    args = parser.parse_args()

    catalog = Catalog(persist_path=args.out)
    orchestrator = Orchestrator(catalog)
    orchestrator.run_phase0(args.data)

    print_report(catalog)
    print(f"\nCatalog snapshot written to {args.out}")


def print_report(catalog: Catalog) -> None:
    print("=" * 72)
    print("GOVERNANCE CATALOG — Phase 0 (AG-02 Discovery, AG-03 Classification)")
    print("=" * 72)

    for dataset in catalog.all_datasets():
        print(f"\n[{dataset.name}]  {dataset.row_count} rows  ·  {dataset.source_path}")
        for column in dataset.columns:
            tags = f" tags={column.regulatory_tags}" if column.regulatory_tags else ""
            nulls = f", nulls={column.null_count}" if column.null_count else ""
            print(
                f"    {column.name:<14} {column.inferred_type:<8} "
                f"sensitivity={column.sensitivity:<11}{tags}{nulls}"
            )

    issues = catalog.open_issues()
    print(f"\n{'-' * 72}")
    print(f"OPEN ISSUES (AG-11): {len(issues)}")
    for issue in issues:
        print(
            f"  {issue.id}  {issue.dataset}.{issue.column}  "
            f"assigned={issue.assigned_to}  sla={issue.sla_hours}h"
        )
        print(f"        {issue.detail}")


if __name__ == "__main__":
    main()
