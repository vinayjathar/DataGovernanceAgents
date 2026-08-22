# Governance Agent Registry — Phase 0 Reference Implementation

A working slice of the multi-agent data governance system designed in
[Governance Agent Registry](https://claude.ai/code/artifact/6e2b72bd-4a66-456a-81dc-af4ca6545a9c).
This repo implements **Phase 0 — Foundation** from that design's rollout
plan: enough of the orchestrator, catalog, and two agents to actually
run end to end against a sample dataset, not just describe how they'd
work.

## What's implemented

| Agent | Role | Authority |
|---|---|---|
| `AG-01` Orchestrator | Wires the event bus and agents together | recommend |
| `AG-02` Discovery & Cataloging | Scans CSVs, infers schema, registers the catalog | auto-act |
| `AG-03` Classification & Sensitivity | Detects PII, labels sensitivity, flags unapproved locations | recommend / escalate |
| `AG-11` Issue & Remediation | Opens a ticket when AG-03 raises an exception | auto-act |

Everything else in the 14-agent design (Quality, Lineage, Policy,
Access, MDM, Retention, Audit, Risk, Guardrail — see the design doc's
Phase 1–3) is scoped but not yet built here.

Zero external dependencies — standard library only (`csv`, `re`,
`dataclasses`, `json`, `unittest`). Requires Python 3.10+.

## Run it

```bash
python3 scripts/run_phase0.py
```

This scans `mock_data/`, publishes `dataset.discovered` events through
the bus, lets `AG-03` classify every column, and prints the resulting
catalog plus any open issues. A JSON snapshot of the catalog is written
to `output/catalog.json` (gitignored).

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

## The mock dataset, and why it looks the way it does

`mock_data/` has three tables with deliberately planted problems, so
the pipeline has something real to catch:

- **`customers.csv`** — `email`, `phone`, and `ssn` are declared PII
  columns the policy already approves. AG-03 labels them
  `sensitivity=restricted` and stops there — no ticket, because this is
  where that data is supposed to be. It also has a duplicate row and a
  missing email — left untouched on purpose, since deduplication and
  completeness rules belong to `AG-09` and `AG-04`, both Phase 1.
- **`orders.csv`** — the free-text `notes` column has an email address
  and a Social Security number typed into it by mistake. Policy has no
  approved-PII entry for `orders.notes`, so AG-03 publishes
  `classification.exception` and AG-11 opens `ISS-001`, assigned to the
  Data Steward — this is workflow 5.3 from the design doc, running for
  real.
- **`products.csv`** — reference data with no sensitive columns, a
  clean control case.

Policy zones live in `governance/agents/classification.py` as
`DEFAULT_APPROVED_ZONES` — edit that dict to change what counts as an
approved location for a given dataset/column pair.

## Project structure

```
governance/
  events.py                 EventBus — sync pub/sub, the "Event Bus" in the architecture diagram
  catalog.py                Catalog — the shared substrate every agent reads/writes
  agents/
    base.py                 Agent base class + Authority enum (auto-act / recommend / escalate)
    discovery.py             AG-02
    classification.py        AG-03
    issue.py                  AG-11
    orchestrator.py            AG-01 — wires bus + catalog + agents
mock_data/                  customers.csv, orders.csv, products.csv
scripts/
  run_phase0.py             CLI entrypoint
tests/
  test_discovery.py
  test_classification.py
output/                     catalog.json snapshot (gitignored, created on run)
```

## Next

Phase 1 (Core Controls) adds `AG-04` Data Quality, `AG-06` Metadata &
Glossary, `AG-07` Policy & Compliance, and `AG-08` Access & Entitlement
behind the same event bus — see the design doc's Rollout section for
the full sequence.
