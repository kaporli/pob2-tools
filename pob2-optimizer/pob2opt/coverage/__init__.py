"""Mechanics coverage (P06-T01 to T03).

``registry``    versioned MechanicRule entries, dependency closure, hashes
``flicker_v1``  the seeded registry for the Flicker seed and flicker_sustained_v1
``inputs``      offline readers: PoB XML, engine parse verdicts, config options, scenarios
``analysis``    candidate coverage, DataGaps and the eligibility decision
``resolution``  evidence resolution, contradiction handling, patch invalidation
"""

from .analysis import CoverageReport, Decision, Finding, analyse, decide
from .registry import MechanicsRegistry, RegistryError, RuleEntry, make_rule
from .resolution import (CoverageLedger, EntityDiff, Resolution,
                         ResolutionRefused)

__all__ = [
    "CoverageLedger", "CoverageReport", "Decision", "EntityDiff", "Finding",
    "MechanicsRegistry", "RegistryError", "Resolution", "ResolutionRefused",
    "RuleEntry", "analyse", "decide", "make_rule",
]
