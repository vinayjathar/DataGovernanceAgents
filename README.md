# Governance Agent Registry — Reference Implementation

A working implementation of the multi-agent data governance system
designed in [Governance Agent Registry](https://claude.ai/code/artifact/6e2b72bd-4a66-456a-81dc-af4ca6545a9c),
with a companion [Codebase Map](https://claude.ai/code/artifact/e4fb8082-bbb3-40fd-aaaa-349e1a339286)
showing how the modules fit together.

All four rollout phases are built: **14 agents**, coordinated over an
event bus, writing to one shared catalog. Zero external dependencies —
standard library only. Requires Python 3.10+.

## Run it

```bash
python3 scripts/run_all.py
```

Runs every phase against the mock dataset and prints a section per
agent, ending in the governance scorecard. Pin the clock for a
reproducible run (retention is date-sensitive):

```bash
python3 scripts/run_all.py --as-of 2026-08-22
```

Phase 0 alone, exactly as it behaved before the later phases existed:

```bash
python3 scripts/run_phase0.py
```

Tests:

```bash
python3 -m unittest discover -s tests
```

## The agents

| Phase | Agent | Does | Authority |
|---|---|---|---|
| 0 | `AG-01` Orchestrator | Wires the bus, fixes pass ordering | recommend |
| 0 | `AG-02` Discovery | Scans sources, infers schema, registers the catalog | auto-act |
| 0 | `AG-03` Classification | Detects PII, labels sensitivity, flags unapproved locations | recommend |
| 0 | `AG-11` Issue & Remediation | Single intake — routes every finding to an owner with an SLA | auto-act |
| 1 | `AG-04` Data Quality | Completeness, uniqueness, validity profiling | auto-act |
| 1 | `AG-06` Metadata & Glossary | Links columns to business terms, drafts definitions, flags conflicts | recommend |
| 1 | `AG-07` Policy & Compliance | Evaluates the catalog against policy-as-code rules | recommend |
| 1 | `AG-08` Access & Entitlement | Auto-approves low-risk requests, escalates the rest | auto-act / escalate |
| 2 | `AG-05` Lineage & Impact | Builds the pipeline graph, propagates sensitivity downstream | auto-act |
| 2 | `AG-09` MDM & Reference Data | Matches and merges records into proposed golden records | recommend |
| 2 | `AG-10` Retention & Lifecycle | Schedules, disposition, legal holds | recommend |
| 2 | `AG-13` Risk & AI-Governance | Risk scoring; gates data used for model training | escalate |
| 2 | `AG-14` Developer Guardrail | Pre-merge governance checks on schema diffs | auto-act |
| 3 | `AG-12` Audit & Monitoring | Taps every event; builds the trail and scorecard | auto-act |

**Authority** is the load-bearing concept: it decides whether a human
sees an action before or after it happens, independent of how confident
the agent is. `AG-09` will never merge an identity on its own; `AG-14`
will block a merge without asking anyone.

## Phases are a rollout, not a switch

Agents from a phase you have not rolled out are constructed but never
subscribed, so they cannot act. `run_phase0()` therefore still behaves
exactly as it did when Phase 0 was all that existed — which is what the
`PhaseGatingTests` in `tests/test_orchestration.py` pin down.

Ordering inside `run_all()` is load-bearing: each agent asserts over
what earlier ones wrote. Policy runs after glossary and ownership
because two of its rules check exactly those; risk runs after lineage
and access because its score reads both.

## What the mock data is for

`mock_data/` has four tables with deliberately planted problems, so
every agent has something real to catch rather than a happy path:

- **`customers.csv`** — approved PII columns (labeled, no ticket), plus
  a duplicate row and a missing required email for `AG-04` to find.
- **`orders.csv`** — an email and an SSN typed into the free-text
  `notes` column. Not an approved location, so `AG-03` raises an
  exception, `AG-07` breaches POL-001, and `AG-08` escalates access to
  a table that otherwise looks purely operational.
- **`legacy_customers.csv`** — the same people in an older system with
  a string `cust_id` instead of an integer, which surfaces a real
  glossary type conflict and gives `AG-09` a cross-system match to
  resolve. Absent from the owner registry, so `AG-07` flags it unowned.
- **`products.csv`** — clean reference data, the control case.

Everything the agents treat as policy lives in `config/`, not in code:
approved zones and rules (`policy_rules.json`), quality rules, the
glossary, pipeline definitions, retention schedules, owners, access
requests, training manifests, and a proposed schema change for the
guardrail to review.

## Project structure

```
governance/
  events.py                 EventBus — pub/sub, plus subscribe_all for AG-12
  catalog.py                The shared substrate: every agent's output lands here
  sources.py                Reading source systems
  policy_engine.py          Policy-as-code rule evaluator (AG-07 runs on this)
  agents/
    base.py                 Agent base class + Authority enum
    orchestrator.py         AG-01 — phase wiring and pass ordering
    discovery.py            AG-02        quality.py       AG-04
    classification.py       AG-03        glossary.py      AG-06
    issue.py                AG-11        policy.py        AG-07
    lineage.py              AG-05        access.py        AG-08
    mdm.py                  AG-09        retention.py     AG-10
    audit.py                AG-12        risk.py          AG-13
    guardrail.py            AG-14
config/                     Policy, rules, glossary, schedules, requests
mock_data/                  Four CSVs with planted governance problems
scripts/
  run_phase0.py             Phase 0 only
  run_all.py                Every phase, with a full report
tests/                      87 tests, stdlib unittest
output/                     Catalog snapshots (gitignored, created on run)
```

## Where this stops

It is a reference implementation, not a deployment. The gaps that
matter most:

- **Sources are CSVs.** Real connectors (warehouse, lake, SaaS) are the
  first thing to add — see the design doc's "Further Skills".
- **Enforcement is advisory.** `AG-08` records a decision but does not
  call an IAM system; `AG-10` recommends disposal but deletes nothing.
- **Classification is regex-based.** Good enough to demonstrate the
  exception path, not good enough for production recall.
- **Nobody grades the agents.** The design doc's "govern the governors"
  loop — evaluating `AG-03`'s recall and `AG-08`'s accuracy against
  labeled cases — is not built.
