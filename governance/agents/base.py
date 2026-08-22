"""Shared shape for every agent: an id, a name, and a fixed authority level.

The authority level is what the design registry keys workflow branching
on — it is not a measure of how "smart" the agent is, only how far it may
act before a human has to sign off.
"""

from __future__ import annotations

from enum import Enum


class Authority(str, Enum):
    AUTO_ACT = "auto-act"
    RECOMMEND = "recommend"
    ESCALATE = "escalate"


class Agent:
    agent_id: str
    name: str
    authority: Authority

    def __init__(self, bus, catalog) -> None:
        self.bus = bus
        self.catalog = catalog
