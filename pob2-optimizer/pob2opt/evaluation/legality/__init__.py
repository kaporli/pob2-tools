"""Legality validation against catalog rules (P02-T03).

What this package owns:

* ``LegalityValidator.validate(build, profile)``: class and ascendancy
  membership, level, point budgets, connected passive allocation, passive
  choices, socketed entities, equipment slots and hands, item level and
  attribute requirements, item construction, skill and support restrictions,
  gem levels, reservation resources and weapon-set rules;
* verification of allocation and equipment against the engine after an exact
  import, because a document PoB accepts is not thereby a legal build;
* the separation of ``illegal`` from ``unknown``, and a cited ``DataGap`` on
  every unknown.

What it does not do: repair a build, infer a rule the patch profile does not
carry, or treat an undecidable check as a pass. Equipment slot legality is
undecidable on a profile exported from the current engine, and this package
says so rather than guessing which bases fit which slot.
"""

from __future__ import annotations

from .checks import CHECKS
from .context import Context, Equipped, RuleView, build_context
from .engine import read_imported_state
from .gaps import GAP_PREFIX, GapFactory, TEMPLATES, raise_gap
from .inputs import (ATTRIBUTES, POOLS, CatalogIndex, ImportedGem,
                     ImportedGroup, ImportedItem, ImportedState, MeasuredState,
                     PoolState, native_key, normalize_id)
from .report import (CHECK_ASCENDANCY, CHECK_ASCENDANCY_BUDGET, CHECK_CHOICES,
                     CHECK_CLASS, CHECK_CONNECTIVITY, CHECK_GEM_LEVELS,
                     CHECK_HANDS, CHECK_IMPORT, CHECK_ITEM_CONSTRUCTION,
                     CHECK_ITEM_REQUIREMENTS, CHECK_LEVEL,
                     CHECK_PASSIVE_BUDGET, CHECK_RESERVATION, CHECK_SKILLS,
                     CHECK_SLOTS, CHECK_SOCKETED, CHECK_SUPPORTS,
                     CHECK_WEAPON_SETS, DECLARED_CHECKS, VALIDATOR_VERSION,
                     CheckOutcome, Constraint, Finding, LegalityReport,
                     ReportBuilder)
from .validator import LegalityValidator

__all__ = [
    "ATTRIBUTES", "CHECKS", "CHECK_ASCENDANCY", "CHECK_ASCENDANCY_BUDGET",
    "CHECK_CHOICES", "CHECK_CLASS", "CHECK_CONNECTIVITY", "CHECK_GEM_LEVELS",
    "CHECK_HANDS", "CHECK_IMPORT", "CHECK_ITEM_CONSTRUCTION",
    "CHECK_ITEM_REQUIREMENTS", "CHECK_LEVEL", "CHECK_PASSIVE_BUDGET",
    "CHECK_RESERVATION", "CHECK_SKILLS", "CHECK_SLOTS", "CHECK_SOCKETED",
    "CHECK_SUPPORTS", "CHECK_WEAPON_SETS", "CatalogIndex", "CheckOutcome",
    "Constraint", "Context", "DECLARED_CHECKS", "Equipped", "Finding",
    "GAP_PREFIX", "GapFactory", "ImportedGem", "ImportedGroup", "ImportedItem",
    "ImportedState", "LegalityReport", "LegalityValidator", "MeasuredState",
    "POOLS", "PoolState", "ReportBuilder", "RuleView", "TEMPLATES",
    "VALIDATOR_VERSION", "build_context", "native_key", "normalize_id",
    "raise_gap", "read_imported_state",
]
