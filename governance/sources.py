"""Reading source systems.

Agents that need actual record values (AG-04 profiling, AG-09 matching)
re-read the source rather than pulling them from the catalog — the
catalog holds metadata about data, never the data itself.
"""

from __future__ import annotations

import csv
from pathlib import Path


def read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]
