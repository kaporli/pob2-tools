"""Coverage resolutions the Flicker evaluator applies (P07-T01).

Three sources, each through ``CoverageLedger.resolve`` so the registry hash,
history and superseded evaluations record them:

1. ``p09_t012``: the P09-T01.2 rule table's ledger resolutions
   (``mechanics-rules.json#/p06_ledger_resolutions``), applied where the
   coverage report has a gap for that mechanic.
2. ``implementation``: rules this package implements and tests (mana
   regeneration with one flask, mana sustain over the window, the rotation
   state paths). Validation means the fixture tests in
   ``tests/unit/test_p07_t01_flicker_cycle.py`` check the implementation
   against hand computation, not against gameplay.
3. ``method``: the owner's D07 amendment 2026-10-18 (2), scoped to method
   ``pob-community-v2``. It defines charges as assumed and Hit and Run as
   PoB applies it. These are method definitions, not verified mechanics; a
   different method gets none of them.

Attribution is never resolved here unless a reviewer's acceptance is passed
in explicitly.

Only resolutions that establish a behavioural claim carry an ``outcome``
(Hit and Run's re-enabling action, the attribution table): the ledger compares
outcomes per rule to detect contradicting evidence. Implementation and
method-definition resolutions make no such claim and leave it empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..coverage import CoverageLedger, CoverageReport, Resolution
from ..domain.enums import GapStatus, RuleOwner, RuleSupport, RuleValidation

_ENUMS = {"support": RuleSupport, "validation": RuleValidation, "owner": RuleOwner}


def _typed(changes: Mapping | None) -> dict:
    """Rule fields as the registry's enum types (the ledger does not coerce)."""
    out = dict(changes or {})
    for key, enum in _ENUMS.items():
        if key in out and not isinstance(out[key], enum):
            out[key] = enum(out[key])
    return out

METHOD_ID = "pob-community-v2"
DECISION = "docs/decisions/D07-flicker-strike-objective.md#amendment-2026-10-18-2"
RULES_FILE = "docs/evidence/P09-T01.2/mechanics-rules.json"
IMPL = "pob2opt.combat"
TESTS = "tests/unit/test_p07_t01_flicker_cycle.py"
AT = "2026-10-18T00:00:00Z"


@dataclass(frozen=True)
class Applied:
    source: str
    resolution_id: str
    gap_id: str | None
    mechanic_id: str | None
    #: applied, skipped or not_applied.
    result: str
    detail: str = ""


def _gap_for(report: CoverageReport, ledger: CoverageLedger, mechanic_id: str | None,
             protocol_gap: str | None = None) -> str | None:
    if protocol_gap and protocol_gap in ledger.gaps:
        return protocol_gap
    if mechanic_id is None:
        return None
    for f in report.findings:
        if mechanic_id in f.mechanic_ids and f.gap_id in ledger.gaps:
            return f.gap_id
    return None


def _apply(ledger, report, source, res_id, mechanic_id, *, protocol_gap=None, evidence,
           author, reviewer=None, rule_changes=None, entry_changes=None, input_values=None,
           outcome="", applied: list, defer_to_settled: bool = False) -> None:
    if (defer_to_settled and mechanic_id in ledger.registry
            and ledger.registry[mechanic_id].is_settled()):
        applied.append(Applied(source, res_id, None, mechanic_id, "skipped",
                               "settled evidence for this rule takes precedence over the "
                               "method definition"))
        return
    gap = _gap_for(report, ledger, mechanic_id, protocol_gap)
    if gap is None:
        applied.append(Applied(source, res_id, None, mechanic_id, "skipped",
                               "no open gap names this mechanic in the report"))
        return
    if ledger.gaps[gap].status is not GapStatus.OPEN and not (rule_changes or entry_changes):
        applied.append(Applied(source, res_id, gap, mechanic_id, "skipped", "gap already resolved"))
        return
    if mechanic_id is not None and mechanic_id not in ledger.registry:
        mechanic_id = None
        rule_changes = entry_changes = None
    ledger.resolve(Resolution(
        resolution_id=res_id, gap_id=gap, evidence_ids=tuple(evidence), author=author,
        resolved_at=AT, reviewer=reviewer, mechanic_id=mechanic_id,
        rule_changes=_typed(rule_changes), entry_changes=entry_changes or {},
        input_values=input_values or ({} if (rule_changes or entry_changes) else
                                      {"/resolution/" + res_id: outcome or True}),
        outcome=outcome))
    applied.append(Applied(source, res_id, gap, mechanic_id, "applied",
                           outcome or "rule/input corrected"))


def apply_p09_t012(ledger: CoverageLedger, report: CoverageReport,
                   resolutions: Iterable[Mapping], applied: list) -> None:
    for r in resolutions:
        changes = dict(r.get("rule_changes") or {})
        _apply(ledger, report, "p09_t012", r["resolution_id"], r.get("mechanic_id"),
               protocol_gap=r.get("gap_id"), evidence=r["evidence_ids"], author=r["author"],
               reviewer=r.get("reviewer"), rule_changes=changes,
               input_values=r.get("input_values") or None, outcome=r.get("outcome", ""),
               applied=applied)


def apply_implementation(ledger: CoverageLedger, report: CoverageReport, applied: list) -> None:
    evidence = (TESTS, "docs/evidence/P07-T01/README.md", "docs/evidence/P09-T01.2/replay.json")
    done = {"support": "implemented", "validation": "fixture_checked",
            "implementation_ref": IMPL}
    _apply(ledger, report, "implementation", "p07-t01/mana-flask", "resource/mana-flask",
           evidence=evidence + ("docs/evidence/P09-T01.2/mechanics-rules.json#mana-sustain",),
           author="P07-T01", applied=applied, outcome="",
           rule_changes={**done, "implementation_ref": IMPL + ".mana",
                         "limitations": ["One mana flask from PoB flaskData; policy is a protocol "
                                         "choice; no kill charges; Mageblood alters no flask on "
                                         "the pin."]})
    _apply(ledger, report, "implementation", "p07-t01/mana-sustain", "resource/mana-sustain",
           evidence=evidence, author="P07-T01", applied=applied,
           outcome="",
           rule_changes={**done, "implementation_ref": IMPL + ".timeline",
                         "limitations": ["Actions wait for mana; waiting time counts in the "
                                         "window. Scoped to flicker_sustained_v1."]})
    _apply(ledger, report, "implementation", "p07-t01/charged-staff-buff-window",
           "charges/charged-staff-consumption", protocol_gap="gap-p09-t011-rotation-details",
           evidence=evidence + ("docs/evidence/P09-T01.2/mechanics-rules.json#charged-staff-period",),
           author="P07-T01", applied=applied, outcome="",
           entry_changes={"provides_paths": ["buff.charged_staff.active"]},
           rule_changes={"implementation_ref": IMPL + ".timeline"})


def apply_method(ledger: CoverageLedger, report: CoverageReport, method: str,
                 applied: list) -> None:
    """D07 amendment (2), only for ``pob-community-v2``.

    A rule already settled by reviewed evidence is left alone: the method
    defines what is unknown, it does not overrule evidence.
    """
    if method != METHOD_ID:
        return
    evidence = (DECISION, "docs/evidence/P09-T01.1/seed/manifest.json#owner_decisions",
                RULES_FILE)
    owner = "owner decision (D07 amendment 2026-10-18 (2))"
    method_rule = {"support": "implemented", "validation": "fixture_checked",
                   "implementation_ref": IMPL + ".timeline"}
    charges = ("Method pob-community-v2: Flicker Strike and Charged Staff use the build's maximum "
               "Power Charges as PoB applies them; generation is not modelled. A method "
               "definition, not a verified mechanic.")
    for mid, gap in (("resource/power-charges", "gap-p09-t011-charge-cycle-rules"),
                     ("resource/combo", None), ("support/SupportCulminationPlayerTwo", None),
                     ("support/SupportAilithLineagePlayer", None),
                     ("support/SupportPerpetualChargePlayer", None),
                     ("passive/41751", None), ("passive/61586", None)):
        changes = dict(method_rule, limitations=[charges])
        entry = {"provides_paths": ["state.power_charges"]} if mid == "resource/power-charges" else None
        _apply(ledger, report, "method", "%s/%s" % (METHOD_ID, mid), mid, protocol_gap=gap,
               evidence=evidence, author="P07-T01", reviewer=owner, rule_changes=changes,
               entry_changes=entry, outcome="", applied=applied, defer_to_settled=True)
    _apply(ledger, report, "method", "%s/charged-staff-shared-charges" % METHOD_ID,
           "charges/charged-staff-consumption",
           protocol_gap="gap-p09-t011-charged-staff-shared-charges", evidence=evidence,
           author="P07-T01", reviewer=owner,
           rule_changes=dict(method_rule, limitations=[
               "Method pob-community-v2: Charged Staff consumes the maximum charges after a "
               "Whirling Assault; Flicker Strike uses the maximum after the next one. The buff "
               "lasts per-stack duration x stacks and applies to strikes impacting in "
               "[press end, press end + duration)."]),
           outcome="", applied=applied, defer_to_settled=True)
    _apply(ledger, report, "method", "%s/hit-and-run" % METHOD_ID, "activation/hit-and-run-reuse",
           protocol_gap="gap-p09-t011-hit-and-run-movement", evidence=evidence,
           author="P07-T01", reviewer=owner,
           rule_changes=dict(method_rule, limitations=[
               "Method pob-community-v2: Hit and Run as PoB applies it, re-enabled by Flicker "
               "Strike's own teleport (owner Q5). Not a verified mechanic; the separately "
               "identified conditional model of P09-T01.1 R1."]),
           entry_changes={"satisfied_by": ["skill:FlickerStrikePlayer"]},
           outcome="method:%s:teleport-satisfies" % METHOD_ID, applied=applied,
           defer_to_settled=True)


def apply_attribution(ledger: CoverageLedger, report: CoverageReport,
                      acceptance: Mapping | None, assignments: Mapping[str, str],
                      applied: list) -> None:
    """Accept the attribution table only with an explicit reviewer acceptance."""
    if not acceptance:
        applied.append(Applied("attribution", "attribution/flicker-sustained-v1", None,
                               "attribution/flicker-sustained-v1", "not_applied",
                               "proposed table, no reviewer acceptance supplied"))
        return
    _apply(ledger, report, "attribution", "p07-t01/attribution-accepted",
           "attribution/flicker-sustained-v1", protocol_gap="gap-p09-t011-attribution-rules",
           evidence=tuple(acceptance["evidence_ids"]), author="P07-T01",
           reviewer=acceptance["reviewer"],
           rule_changes={"support": "implemented", "validation": "fixture_checked",
                         "implementation_ref": IMPL + ".attribution"},
           entry_changes={"assignments": dict(assignments)},
           outcome="attribution:%s" % acceptance.get("table_id", "accepted"), applied=applied)
