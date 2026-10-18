"""Candidate coverage analysis and the eligibility decision (P06-T02).

:func:`analyse` walks one build, its rotation and one scenario through the
registry: enabled skill groups on the active weapon sets, their supports,
allocated passives, equipped item lines, applied PoB config, rotation
actions and predicates, and the scenario's own requirements. It resolves the
transitive rule dependencies and returns per-domain states plus findings,
each rendered as a contracts.md ``DataGap``.

:func:`decide` is the call an evaluator must make before a score may count.
It refuses on any open blocking finding or protocol gap and, independently of
gap severity, on any activation or attribution rule that is not implemented,
checked, evidenced and reviewed (P09-T01.1 R1).

Finding classes are distinct so each yields a different request:

``missing_data``           an input value is absent (collect or import it)
``missing_implementation`` the rule is known, no code calculates it
``unknown_rule``           how the game behaves is not established
``unvalidated``            calculated, not checked against evidence
``stale_patch``            the rule or profile does not cover the patch
``unknown_entity``         a build entity no rule covers
``hidden_assumption``      a PoB config value the build does not generate
``activation_unmet``       the rotation never re-enables a gated skill
``unassigned_damage``      a damage source without an ownership class
``conflicting_evidence``   accepted evidence disagrees
``not_applicable``         the scenario supplies nothing for the effect
``unbound_evidence``       parse or config evidence not bound to this document,
                           loadout, engine and state
``loadout``                the document's selected sets cannot be determined
``target_mismatch``        a scenario-owned target value differs or is absent
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ..domain.enums import (CoverageState, GapKind, GapSeverity, GapStatus,
                            RuleSupport, RuleValidation)
from ..domain.identity import content_hash
from ..domain.records import DataGap, RotationPolicy
from ..domain.validation import validate_record
from .inputs import BuildFacts, ConfigOption, ModSupport, ScenarioFacts
from .registry import CHECKED, MechanicsRegistry, RuleEntry

BLOCKING, RANKING, INFO = (GapSeverity.BLOCKING, GapSeverity.RANKING_SENSITIVE,
                           GapSeverity.INFORMATIONAL)

GAP_KIND = {
    "missing_data": GapKind.MISSING_INPUT,
    "missing_implementation": GapKind.UNSUPPORTED_RULE,
    "unknown_rule": GapKind.UNSUPPORTED_RULE,
    "unvalidated": GapKind.UNVALIDATED_PREDICTION,
    "stale_patch": GapKind.STALE_PATCH,
    "unknown_entity": GapKind.UNRESOLVED_ENTITY,
    "hidden_assumption": GapKind.UNSUPPORTED_RULE,
    "activation_unmet": GapKind.UNSUPPORTED_RULE,
    "unassigned_damage": GapKind.UNSUPPORTED_RULE,
    "conflicting_evidence": GapKind.CONFLICTING_EVIDENCE,
    "not_applicable": GapKind.UNVALIDATED_PREDICTION,
    "unbound_evidence": GapKind.MISSING_INPUT,
    "loadout": GapKind.UNRESOLVED_ENTITY,
    "target_mismatch": GapKind.CONFLICTING_EVIDENCE,
}

COLLECTION = {
    "missing_data": "Import or record the named input; a reviewer checks its source.",
    "missing_implementation": "Engine or simulator implementation of the named rule, with a fixture test.",
    "unknown_rule": "Catalog evidence or a manual interaction trial establishing the behaviour, then a rule update through the coverage ledger.",
    "unvalidated": "Fixture or gameplay check of the named rule's output against independent evidence.",
    "stale_patch": "Re-verify the rule against the current patch profile and record the evidence.",
    "unknown_entity": "Registry entry for the entity: owner, dependencies and support status.",
    "hidden_assumption": "Either a rule showing the build generates the state under the rotation, or remove the config value.",
    "activation_unmet": "A rotation that performs a re-enabling action before each use, with its time counted, or evidence that an existing action satisfies the condition.",
    "unassigned_damage": "An accepted attribution class for the damage source in the attribution rule.",
    "conflicting_evidence": "A controlled trial that separates the contradicting results; contradictions are never averaged.",
    "not_applicable": "None for this scenario; a scenario supplying the event would need the rule.",
    "unbound_evidence": "Recapture PoB parse verdicts and config from the exact selected document on a clean checkout of the pinned engine (scripts/p06_seed_engine_mod_support.py).",
    "loadout": "Fix the document's set selectors or loadout titles so exactly one set per tab is selected, then re-import.",
    "target_mismatch": "Set the PoB target configuration to the scenario's value and recapture.",
}

#: Calculation-mode switches. They change how PoB averages, not game state.
MODE_VAR = re.compile(r"Mode$")
#: Variable types PoB applies from a placeholder (ConfigTab:BuildModList).
PLACEHOLDER_TYPES = ("count", "integer", "countAllowZero", "float")

#: Unparsed item or passive text, by what it needs from the scenario.
LINE_EVENTS = (
    ("kill", re.compile(r"\bkill|\bshatter", re.I)),
    ("incoming_hit", re.compile(r"when (you are )?hit|damage taken|recouped|"
                                r"when you become|affected by a slow|bypass your energy shield|"
                                r"energy shield recharge|when hit", re.I)),
)
USE_CONDITION = re.compile(r"^used when ", re.I)
#: Flask lines that act only while the flask's effect runs. No rotation
#: action uses a flask, so they need a ``flask_use`` event.
FLASK_EFFECT = re.compile(r"during (flask )?effect|effect is not removed", re.I)
NO_EFFECT_LINE = re.compile(r"^[+-]?\d+ (prefix|suffix) modifiers? allowed$", re.I)


@dataclass(frozen=True)
class Finding:
    gap_class: str
    domain: str
    severity: GapSeverity
    subject_ids: tuple[str, ...]
    mechanic_ids: tuple[str, ...]
    field_paths: tuple[str, ...]
    explanation: str
    needed_evidence: str
    protocol_gap_ids: tuple[str, ...] = ()

    def identity(self) -> dict:
        return {"class": self.gap_class, "domain": self.domain,
                "subjects": sorted(self.subject_ids),
                "mechanics": sorted(self.mechanic_ids),
                "fields": sorted(self.field_paths)}

    @property
    def gap_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", (self.mechanic_ids or self.subject_ids
                                            or self.field_paths or ("x",))[0].lower()).strip("-")
        return "gap-p06-%s-%s-%s" % (self.gap_class.replace("_", "-"), slug[:40],
                                     content_hash(self.identity())[:10])


@dataclass(frozen=True)
class CoverageReport:
    build_id: str
    scenario_id: str
    rotation_id: str | None
    registry_id: str
    registry_hash: str
    rule_ids: tuple[str, ...]
    rule_closure_hash: str
    critical_rule_ids: tuple[str, ...]
    domains: Mapping[str, Mapping[str, str]]
    findings: tuple[Finding, ...]
    protocol_gaps: tuple[DataGap, ...]
    notes: tuple[str, ...] = ()
    #: Identity of everything the verdicts were checked against: document,
    #: selection, engine, item identities, nodes and config.
    input_identity: str = ""

    def gaps(self, *, created_at: str = "2026-10-18T00:00:00Z") -> list[DataGap]:
        out = []
        for f in self.findings:
            gap = DataGap(
                schema_version=1, record_id=f.gap_id, created_at=created_at,
                provenance_ids=["p06-coverage", self.registry_id],
                gap_id=f.gap_id, kind=GAP_KIND[f.gap_class],
                subject_ids=sorted(set(f.subject_ids) | {self.scenario_id}),
                field_paths=list(f.field_paths), mechanic_ids=list(f.mechanic_ids),
                severity=f.severity, explanation=f.explanation,
                needed_evidence=f.needed_evidence,
                collection_method=COLLECTION[f.gap_class],
                affected_evaluation_ids=[], sensitivity_result_id=None,
                status=GapStatus.OPEN, resolution_evidence_ids=[])
            report = validate_record(gap)
            if not report.ok:
                raise ValueError("invalid gap %s: %s" % (f.gap_id, report.errors))
            out.append(gap)
        return out

    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is BLOCKING]

    def to_json(self) -> dict:
        return {
            "build_id": self.build_id, "scenario_id": self.scenario_id,
            "rotation_id": self.rotation_id, "registry_id": self.registry_id,
            "registry_hash": self.registry_hash, "rule_ids": list(self.rule_ids),
            "rule_closure_hash": self.rule_closure_hash,
            "input_identity": self.input_identity,
            "critical_rule_ids": list(self.critical_rule_ids),
            "domains": {k: dict(v) for k, v in sorted(self.domains.items())},
            "findings": [{"gap_id": f.gap_id, "class": f.gap_class, "domain": f.domain,
                          "severity": f.severity.value, "subjects": list(f.subject_ids),
                          "mechanics": list(f.mechanic_ids), "fields": list(f.field_paths),
                          "protocol_gap_ids": list(f.protocol_gap_ids),
                          "explanation": f.explanation} for f in self.findings],
            "open_protocol_gaps": [{"gap_id": g.gap_id, "kind": g.kind.value,
                                    "severity": g.severity.value}
                                   for g in self.protocol_gaps if g.status is GapStatus.OPEN],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class Decision:
    eligible: bool
    blocking_gap_ids: tuple[str, ...]
    unsettled_critical: tuple[str, ...]
    reasons: tuple[str, ...]


# ===================================================================== walk ===

@dataclass
class _Walk:
    registry: MechanicsRegistry
    scenario: ScenarioFacts
    findings: list[Finding] = field(default_factory=list)
    used: set[str] = field(default_factory=set)
    rotation_used: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def add(self, gap_class, domain, severity, *, subjects=(), mechanics=(),
            fields=(), explanation, needed, protocol=()):
        self.findings.append(Finding(
            gap_class=gap_class, domain=domain, severity=severity,
            subject_ids=tuple(subjects), mechanic_ids=tuple(mechanics),
            field_paths=tuple(fields), explanation=explanation,
            needed_evidence=needed, protocol_gap_ids=tuple(protocol)))

    def use(self, entries: Iterable[RuleEntry], *, rotation: bool = False):
        for e in entries:
            self.used.add(e.mechanic_id)
            if rotation:
                self.rotation_used.add(e.mechanic_id)


def _active_sets(rotation: RotationPolicy | None) -> frozenset[int]:
    if rotation is None:
        return frozenset({1})
    sets = {1}
    for rule in rotation.rules:
        if rule.weapon_set_id:
            digits = re.sub(r"\D", "", rule.weapon_set_id)
            if digits:
                sets.add(int(digits))
    return frozenset(sets)


def _predicate_paths(predicate) -> list[str]:
    out = []
    path = getattr(predicate, "path", None)
    if isinstance(path, str):
        out.append(path)
    operands = getattr(predicate, "operands", None)
    if isinstance(operands, list):
        for op in operands:
            out.extend(_predicate_paths(op))
    return out


def analyse(build: BuildFacts, scenario: ScenarioFacts, registry: MechanicsRegistry, *,
            rotation: RotationPolicy | None = None,
            mod_support: ModSupport | None = None,
            config_options: Mapping[str, ConfigOption] | None = None,
            patch_profile_id: str,
            patch_compatibility: str,
            pinned_commit: str,
            inputs: Mapping[str, object] | None = None) -> CoverageReport:
    w = _Walk(registry, scenario)
    sets = _active_sets(rotation)
    active_groups = [g for g in build.groups if g.enabled and g.sets & sets]
    for g in build.groups:
        if g not in active_groups:
            w.notes.append("group %d not on active weapon sets %s or disabled; not walked"
                           % (g.index, sorted(sets)))
    skill_ids = {s.skill_id for g in active_groups for s in g.active_skills}
    skill_names = {s.name for g in active_groups for s in g.active_skills}

    w.use(registry.for_subject("always"))
    w.use(registry.for_subject("scenario:" + scenario.scenario_id))

    _walk_patch(w, build, patch_profile_id, patch_compatibility)
    _walk_loadout(w, build)
    _walk_engine(w, build, pinned_commit)
    verified = _verify_capture(w, build, mod_support, pinned_commit)
    _walk_skills(w, active_groups)
    _walk_passives(w, build, verified)
    _walk_items(w, build, verified, sets)
    _walk_config(w, build, verified, config_options, skill_names)
    _walk_rotation(w, rotation, active_groups, skill_ids)
    _walk_scenario(w)
    _walk_rules(w, patch_profile_id)
    _walk_inputs(w, build, inputs or {})
    _check_activation(w, active_groups, rotation)
    _check_attribution(w, active_groups, rotation)

    findings = _dedupe(w.findings)
    rule_ids = tuple(registry.closure(w.used))
    critical = tuple(m for m in rule_ids if registry[m].critical)
    return CoverageReport(
        build_id=build.build_id, scenario_id=scenario.scenario_id,
        rotation_id=rotation.rotation_id if rotation else None,
        registry_id=registry.registry_id, registry_hash=registry.registry_hash(),
        rule_ids=rule_ids, rule_closure_hash=registry.closure_hash(rule_ids),
        critical_rule_ids=critical,
        domains=_domain_states(registry, rule_ids, findings),
        findings=findings, protocol_gaps=scenario.protocol_gaps,
        notes=tuple(w.notes),
        input_identity=content_hash({
            "build": build.build_id, "document_hash": build.document_hash,
            "selection": dict(sorted(build.selection.items())),
            "engine": None if build.engine is None else [build.engine.pob_commit,
                                                          build.engine.pob_dirty],
            "items": sorted([i.slot, i.item_id, i.text_sha256] for i in build.items),
            "nodes": list(build.passive_ids),
            "config": {k: build.config_explicit[k] for k in sorted(build.config_explicit)},
            "capture": None if mod_support is None or mod_support.binding is None
            else mod_support.binding.identity(),
        }))


def _dedupe(findings: list[Finding]) -> tuple[Finding, ...]:
    best: dict[str, Finding] = {}
    order = {BLOCKING: 0, RANKING: 1, INFO: 2}
    for f in findings:
        current = best.get(f.gap_id)
        if current is None or order[f.severity] < order[current.severity]:
            best[f.gap_id] = f
    return tuple(sorted(best.values(), key=lambda f: (order[f.severity], f.gap_id)))


# --------------------------------------------------------------- sections ===

def _walk_patch(w, build, profile_id, compatibility):
    if compatibility in ("stale", "unknown"):
        w.add("stale_patch", "patch", BLOCKING, subjects=(profile_id,),
              fields=("/patch_profile/compatibility",),
              explanation="Patch profile %s has compatibility %r; no rule result on it is current."
                          % (profile_id, compatibility),
              needed="Official patch evidence and an engine/catalog review establishing "
                     "compatibility of %s with the current patch." % profile_id)
    if build.declared_patch:
        w.notes.append("build declares %r; the declaration does not override profile "
                       "compatibility %r" % (build.declared_patch, compatibility))


def _walk_loadout(w, build):
    for problem in build.loadout_problems:
        path = problem.split(":", 1)[0]
        w.add("loadout", "build", BLOCKING, subjects=(build.build_id,), fields=(path,),
              explanation="The evaluated loadout cannot be determined: %s. No set is chosen "
                          "in its place." % problem,
              needed="A document whose selectors or loadout links name exactly one set in "
                     "%s." % path)


@dataclass
class _Verified:
    """The parts of a capture that are bound to this exact candidate.

    ``items``/``nodes`` hold only verdicts whose identity matched; ``config``
    is None unless the captured config state equals the candidate's.
    """

    items: dict
    nodes: dict
    config: tuple | None


def _verify_capture(w, build, mods, pinned_commit) -> _Verified | None:
    if mods is None:
        return None

    def unbound(field, explanation, subjects=(build.build_id,)):
        w.add("unbound_evidence", "evidence", BLOCKING, subjects=subjects, fields=(field,),
              explanation=explanation,
              needed="Parse verdicts captured from document %s, selection %s, on a clean "
                     "checkout of %s, covering %s." % (
                         (build.document_hash or "?")[:16], dict(build.selection),
                         pinned_commit, field))

    b = mods.binding
    if b is None:
        unbound("/engine_parse/binding",
                "The parse capture %s names no document, loadout, engine or state, so none "
                "of its verdicts can be attributed to this candidate." % mods.source)
        return _Verified({}, {}, None)
    if build.document_hash is None or b.document_hash != build.document_hash             or dict(b.selection) != dict(build.selection):
        unbound("/engine_parse/binding/document",
                "The capture was taken from document %s selection %s; this candidate is "
                "document %s selection %s." % (
                    b.document_hash[:16], dict(b.selection),
                    (build.document_hash or "unknown")[:16], dict(build.selection)))
        return _Verified({}, {}, None)
    if b.pob_commit != pinned_commit or mods.pob_commit != b.pob_commit or b.pob_dirty is not False:
        unbound("/engine_parse/binding/engine",
                "The capture ran on %s (dirty=%s); verdicts count only from a clean %s."
                % (b.pob_commit, b.pob_dirty, pinned_commit))
        return _Verified({}, {}, None)
    items = {}
    for item in build.items:
        identity = b.items.get(item.slot)
        if item.text_sha256 is None or identity is None                 or tuple(identity) != (item.item_id, item.text_sha256):
            unbound("/engine_parse/items/" + item.slot,
                    "Slot %s holds item %s (text %s); the capture saw %s." % (
                        item.slot, item.item_id, (item.text_sha256 or "unknown")[:16],
                        "nothing" if identity is None else "%s (text %s)" % (
                            identity[0], str(identity[1])[:16])),
                    subjects=("item:" + item.slot,))
        elif item.slot in mods.items:
            items[item.slot] = mods.items[item.slot]
    captured_nodes = set(b.nodes)
    nodes = {}
    for node in build.passive_ids:
        if node not in captured_nodes:
            unbound("/engine_parse/nodes/" + node,
                    "Passive %s is allocated but was not allocated when the capture ran."
                    % node, subjects=("passive:" + node,))
        elif node in mods.nodes:
            nodes[node] = mods.nodes[node]
    for node in sorted(captured_nodes - set(build.passive_ids), key=str):
        unbound("/engine_parse/nodes/" + node,
                "The capture had passive %s allocated; this candidate does not." % node,
                subjects=("passive:" + node,))
    config = None
    if _same_config(b.config, build.config_explicit):
        config = mods.config
        if config is not None:
            seen = {r["var"]: r.get("input") for r in config}
            for var, value in sorted(build.config_explicit.items()):
                if not _same_value(seen.get(var), value):
                    unbound("/config/" + var,
                            "The captured config rows show %s = %r; the candidate sets %r."
                            % (var, seen.get(var), value))
                    config = None
    else:
        changed = sorted(set(b.config) ^ set(build.config_explicit)
                         | {k for k in set(b.config) & set(build.config_explicit)
                            if not _same_value(b.config[k], build.config_explicit[k])})
        unbound("/config",
                "The capture's config state differs from the candidate's in %s."
                % ", ".join(changed))
    return _Verified(items, nodes, config)


def _same_value(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b and type(a) is type(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    if isinstance(a, str) and isinstance(b, str):
        # XML attribute normalisation turns newlines and tabs into spaces;
        # PoB keeps them. Whitespace runs are one value either way.
        return a.split() == b.split()
    return a == b


def _same_config(a, b) -> bool:
    return set(a) == set(b) and all(_same_value(a[k], b[k]) for k in a)


def _walk_engine(w, build, pinned_commit):
    engine = build.engine
    if engine is None or engine.pob_commit is None or engine.pob_dirty is None:
        w.add("missing_data", "engine", BLOCKING, subjects=(build.build_id,),
              mechanics=("engine/pinned-checkout",),
              fields=("/engine/pob_commit", "/engine/pob_dirty"),
              explanation="The engine checkout that produced this build's PoB outputs is not "
                          "recorded with a clean-tree check.",
              needed="PoB outputs for this build rerun on a checkout at %s with an empty "
                     "git status, recorded with the commit and status." % pinned_commit,
              protocol=registry_gaps(w, "engine/pinned-checkout"))
    elif engine.pob_commit != pinned_commit or engine.pob_dirty:
        w.add("stale_patch", "engine", BLOCKING, subjects=(build.build_id,),
              mechanics=("engine/pinned-checkout",), fields=("/engine/pob_commit",),
              explanation="Outputs come from %s (dirty=%s), not the clean pin %s."
                          % (engine.pob_commit, engine.pob_dirty, pinned_commit),
              needed="Rerun on a clean checkout of %s." % pinned_commit)


def registry_gaps(w, mechanic_id) -> tuple[str, ...]:
    if mechanic_id in w.registry:
        return w.registry[mechanic_id].protocol_gap_ids
    return ()


def _walk_skills(w, groups):
    generic_supports = []
    for g in groups:
        for skill in g.active_skills:
            entries = w.registry.for_subject("skill:" + skill.skill_id)
            if entries:
                w.use(entries)
            else:
                w.add("unknown_entity", "skill", BLOCKING,
                      subjects=("skill:" + skill.skill_id,),
                      explanation="Active skill %s (%s) in group %d has no registry rule: its "
                                  "damage, triggers and conditions have no owner."
                                  % (skill.skill_id, skill.name, g.index),
                      needed="A registry entry for %s naming its owner, dependencies, "
                             "conditions and support status." % skill.skill_id)
        for sup in g.supports:
            entries = w.registry.for_subject("support:" + sup.skill_id)
            if entries:
                w.use(entries)
            else:
                generic_supports.append(sup.skill_id)
                w.use(w.registry.for_subject("support:*"))
    if generic_supports:
        w.add("unvalidated", "support", RANKING,
              subjects=tuple(sorted({"support:" + s for s in generic_supports})),
              mechanics=("damage/pob-modifiers",),
              explanation="Supports without a specific rule fall back to PoB's parsed "
                          "modifiers; conditional or triggered effects are not checked.",
              needed="For each listed support, a registry entry stating whether its effect "
                     "is unconditional, with a fixture comparing PoB output with and without it.")


def _classify_line(text, scenario_events, inherited=None):
    """(event needed or None, class) for an unparsed line."""
    if inherited:
        return inherited
    for event, pattern in LINE_EVENTS:
        if pattern.search(text):
            return event
    return None


def _line_finding(w, domain, subject, text, line, inherited_event=None):
    event = _classify_line(text, w.scenario.events, inherited_event)
    if not line.parsed and not line.extra and NO_EFFECT_LINE.match(text.strip()):
        return
    if not line.parsed and not line.extra:
        w.add("unvalidated", domain, RANKING, subjects=(subject,), fields=(text,),
              explanation="PoB returns no modifier and no unparsed remainder for %r on %s; "
                          "any effect is applied elsewhere or not at all." % (text, subject),
              needed="A PoB output comparison with and without the line on %s, or a "
                     "source showing where PoB applies it." % subject)
        return
    if event and event not in w.scenario.events:
        w.add("not_applicable", domain, INFO, subjects=(subject,), fields=(text,),
              explanation="PoB does not parse %r on %s; it needs %s events, which %s does "
                          "not supply, so it adds nothing here." % (
                              text, subject, event, w.scenario.scenario_id),
              needed="Only for a scenario with %s events: an implementation of the line." % event)
        return
    w.add("missing_implementation", domain, BLOCKING, subjects=(subject,), fields=(text,),
          explanation="PoB does not parse %r on %s (unparsed remainder %r); its effect is "
                      "not calculated." % (text, subject, line.extra),
          needed="An engine or simulator implementation of %r with a fixture test, or "
                 "evidence that it has no effect in %s." % (text, w.scenario.scenario_id))


def _walk_passives(w, build, verified):
    for node in build.passive_ids:
        entries = w.registry.for_subject("passive:" + node)
        w.use(entries or w.registry.for_subject("passive:*"))
        if entries or verified is None:
            continue
        lines = verified.nodes.get(node)
        if lines is None:
            w.add("missing_data", "passive", BLOCKING, subjects=("passive:" + node,),
                  fields=("/engine_parse/nodes/" + node,),
                  explanation="No bound PoB parse verdict for allocated passive %s and no "
                              "registry rule covers it." % node,
                  needed="PoB's per-line parse verdicts for passive %s from the bound "
                         "capture, or a registry rule for it." % node)
            continue
        for line in lines:
            if not line.parsed or line.extra:
                _line_finding(w, "passive", "passive:" + node, line.line, line)
    if verified is None and build.passive_ids:
        w.add("missing_data", "passive", BLOCKING, subjects=(build.build_id,),
              fields=("/engine_parse/nodes",),
              explanation="Which allocated passive lines PoB parses is not recorded, so "
                          "unsupported passive text cannot be detected.",
              needed="Per-line PoB parse verdicts for every allocated node "
                     "(scripts/p06_seed_engine_mod_support.py output).")


def _walk_items(w, build, verified, sets):
    if not build.items:
        return
    w.use(w.registry.for_subject("item:*"))
    if verified is None:
        w.add("missing_data", "item", BLOCKING, subjects=(build.build_id,),
              fields=("/engine_parse/items",),
              explanation="Which equipped item lines PoB parses is not recorded, so unknown "
                          "item modifiers cannot be detected.",
              needed="Per-line PoB parse verdicts for every equipped item "
                     "(scripts/p06_seed_engine_mod_support.py output).")
        return
    for item in build.items:
        swap = "Swap" in item.slot
        if swap and 2 not in sets:
            w.notes.append("%s (%s) is on weapon set 2, not walked" % (item.slot, item.name))
            continue
        lines = verified.items.get(item.slot)
        if lines is None:
            w.add("missing_data", "item", BLOCKING, subjects=("item:" + item.slot,),
                  fields=("/engine_parse/items/" + item.slot,),
                  explanation="No bound PoB parse verdicts for %s (%s)." % (item.slot, item.name),
                  needed="PoB parse verdicts for the item in %s from the bound capture."
                         % item.slot)
            continue
        inherited = None
        if item.slot.startswith("Flask") and any(FLASK_EFFECT.search(l.line) for l in lines):
            inherited = "flask_use"
        for line in lines:
            if USE_CONDITION.match(line.line) and (not line.parsed or line.extra):
                inherited = _classify_line(line.line, w.scenario.events)
        for line in lines:
            if not line.parsed or line.extra:
                _line_finding(w, "item", "item:" + item.slot, line.line, line, inherited)


def _walk_config(w, build, verified, options, skill_names):
    rows = []
    if verified is not None and verified.config is not None:
        rows = list(verified.config)
    else:
        effective = dict(build.config_explicit)
        if build.config_effective is not None:
            effective.update(build.config_effective)
        else:
            if options is not None:
                for var, opt in options.items():
                    if var not in effective and opt.default not in (None, False) \
                            and _gate_open(opt, skill_names, effective):
                        effective[var] = opt.default
            w.add("missing_data", "config", BLOCKING, subjects=(build.build_id,),
                  fields=("/config/effective",),
                  explanation="No bound engine config capture: PoB's default-on options and "
                              "placeholders are not observed for this candidate.",
                  needed="The engine's effective config input and placeholders for this build.")
        rows = [{"var": k, "shown": None, "input": v, "placeholder": None}
                for k, v in effective.items()]
    targets = dict(w.scenario.target_config)
    seen_targets = set()
    for row in sorted(rows, key=lambda r: r["var"]):
        var = row["var"]
        if var.startswith("quest"):
            continue
        opt = options.get(var) if options else None
        value = row.get("input")
        if value is None and row.get("placeholder") is not None:
            if opt is None or opt.type in PLACEHOLDER_TYPES:
                value = row["placeholder"]
        if value is None or value is False:
            continue
        shown = row.get("shown")
        if shown is None and opt is not None:
            shown = True if _gate_open(opt, skill_names, {}) else None
        subject = "config:" + var
        if var in targets:
            seen_targets.add(var)
            if _same_value(value, targets[var]):
                w.use(e for e in w.registry.for_subject("scenario:" + w.scenario.scenario_id)
                      if e.domain == "target")
            else:
                w.add("target_mismatch", "target", BLOCKING, subjects=(subject,),
                      fields=("/config/" + var,),
                      explanation="PoB applies %s = %r; scenario %s fixes it at %r."
                                  % (var, value, w.scenario.scenario_id, targets[var]),
                      needed="%s set to %r and PoB outputs recaptured." % (var, targets[var]))
            continue
        if shown is False:
            w.add("not_applicable", "config", INFO, subjects=(subject,), fields=("/config/" + var,),
                  explanation="%s = %r is applied but PoB hides the option for this build; its "
                              "condition does not hold." % (var, value),
                  needed="Only if the build changes: a rule generating the state.")
            continue
        entries = w.registry.for_subject(subject)
        if entries:
            applicable = [e for e in entries
                          if not set(e.requires_events) - w.scenario.events]
            if not applicable:
                w.add("not_applicable", "config", INFO, subjects=(subject,),
                      fields=("/config/" + var,),
                      explanation="%s = %r feeds %s, which needs events %s does not supply."
                                  % (var, value, ", ".join(e.mechanic_id for e in entries),
                                     w.scenario.scenario_id),
                      needed="Only for a scenario with those events: the rule's evidence.")
                continue
            w.use(applicable)
            bound = {}
            for e in applicable:
                bound.update(e.config_values)
            if var not in bound or not _same_value(bound[var], value):
                w.add("hidden_assumption", "config", BLOCKING, subjects=(subject,),
                      mechanics=tuple(e.mechanic_id for e in applicable),
                      fields=("/config/" + var,),
                      explanation="PoB applies %s = %r; rule %s establishes %s." % (
                          var, value, ", ".join(e.mechanic_id for e in applicable),
                          "no value for it" if var not in bound else repr(bound[var])),
                      needed="Evidence fixing the magnitude and uptime of %s under the "
                             "rotation, recorded as the rule's value." % var)
            continue
        if MODE_VAR.search(var):
            w.add("unvalidated", "config", RANKING, subjects=(subject,), fields=("/config/" + var,),
                  explanation="Calculation mode %s = %r changes how PoB averages outcomes." % (var, value),
                  needed="A comparison of PoB output across the modes of %s for this build." % var)
            continue
        if "config/condition-sustain" in w.registry:
            w.used.add("config/condition-sustain")
        w.add("hidden_assumption", "config", BLOCKING, subjects=(subject,),
              mechanics=("config/condition-sustain",), fields=("/config/" + var,),
              explanation="PoB applies %s = %r%s; nothing shows the build generates it under "
                          "the rotation (D07: no free state toggles)."
                          % (var, value, "" if shown else " (visibility unknown)"),
              needed="A registry rule deriving %s from the rotation's state, or the value "
                     "removed and PoB outputs recaptured." % var,
              protocol=registry_gaps(w, "config/condition-sustain"))
    for var in sorted(set(targets) - seen_targets):
        w.add("target_mismatch", "target", BLOCKING, subjects=("config:" + var,),
              fields=("/config/" + var,),
              explanation="Scenario %s fixes %s = %r; the capture shows no value for it."
                          % (w.scenario.scenario_id, var, targets[var]),
              needed="%s applied at %r in a bound capture." % (var, targets[var]))


def _gate_open(opt, skill_names, effective) -> bool | None:
    if not opt.gates:
        return True
    for key, values in opt.gates.items():
        if key == "ifSkill":
            if any(v in skill_names for v in values):
                return True
            return False
        if key == "ifOption":
            return any(effective.get(v) for v in values)
    return None


def _walk_rotation(w, rotation, groups, skill_ids):
    if rotation is None:
        w.add("missing_data", "rotation", BLOCKING, subjects=(w.scenario.scenario_id,),
              fields=("/rotation",),
              explanation="No rotation policy: action order, waits and resource use are unknown.",
              needed="A RotationPolicy for this build and scenario with every action and "
                     "predicate stated.",
              protocol=tuple(g.gap_id for g in w.scenario.protocol_gaps
                             if g.gap_id.endswith("rotation-details")))
        return
    for rule in rotation.rules:
        kind = rule.action.value
        if kind == "use_skill":
            sid = rule.skill_id or ""
            if sid not in skill_ids:
                w.add("missing_data", "rotation", BLOCKING, subjects=("skill:" + sid,),
                      fields=("/rules/%d/skill_id" % rule.rule_index,),
                      explanation="Rotation action %s uses %s, which no enabled group on the "
                                  "active weapon sets provides." % (rule.action_id, sid),
                      needed="The skill socketed and enabled on the weapon set the action names.")
            else:
                w.use(w.registry.for_subject("skill:" + sid), rotation=True)
                for g in groups:
                    if any(s.skill_id == sid for s in g.active_skills):
                        for sup in g.supports:
                            w.use(w.registry.for_subject("support:" + sup.skill_id), rotation=True)
        elif kind in ("move", "switch_weapon_set"):
            path = "action.%s.duration" % kind
            providers = w.registry.providing(path)
            if providers:
                w.use(providers, rotation=True)
            else:
                w.add("missing_implementation", "rotation", BLOCKING,
                      subjects=(rule.action_id,), fields=(path,),
                      explanation="Rotation action %s (%s) has no rule giving its duration, so "
                                  "its time cannot be counted." % (rule.action_id, kind),
                      needed="A movement or weapon-swap timing rule with evidence for %s." % path,
                      protocol=tuple(g.gap_id for g in w.scenario.protocol_gaps
                                     if g.gap_id.endswith("movement-model")))
        for path in _predicate_paths(rule.predicate):
            providers = w.registry.providing(path)
            if not providers:
                w.add("missing_implementation", "rotation", BLOCKING,
                      subjects=(rule.action_id,), fields=(path,),
                      explanation="Predicate path %s in action %s has no rule producing it."
                                  % (path, rule.action_id),
                      needed="A rule that produces %s from the build and rotation." % path)
                continue
            w.use(providers, rotation=True)
            usable = [p for p in providers
                      if not (set(p.requires_events) - w.scenario.events)]
            if not usable:
                w.add("missing_data", "rotation", BLOCKING, subjects=(rule.action_id,),
                      mechanics=tuple(p.mechanic_id for p in providers), fields=(path,),
                      explanation="Action %s waits on %s, which only event-driven rules produce; "
                                  "%s supplies none of those events." % (
                                      rule.action_id, path, w.scenario.scenario_id),
                      needed="A source of %s that works without those events." % path)


def _walk_scenario(w):
    for path, gap_ids in sorted(w.scenario.missing_fields.items()):
        w.add("missing_data", "scenario", BLOCKING, subjects=(w.scenario.scenario_id,),
              fields=(path,),
              explanation="Scenario field %s has no value." % path,
              needed="The value of %s from the evidence its protocol gap names." % path,
              protocol=gap_ids)


def _walk_rules(w, profile_id):
    reg = w.registry
    unvalidated: dict[str, list[str]] = {}
    for mid in reg.closure(w.used):
        e = reg[mid]
        rule = e.rule
        protocol = e.protocol_gap_ids
        if e.critical == "activation":
            continue
        missing_events = set(e.requires_events) - w.scenario.events
        if missing_events and not e.critical:
            w.add("not_applicable", e.domain, INFO, mechanics=(mid,),
                  subjects=e.subject_ids,
                  explanation="%s needs %s events; %s supplies none, so it adds nothing."
                              % (mid, ", ".join(sorted(missing_events)), w.scenario.scenario_id),
                  needed="Only for a scenario with %s events: validation of %s."
                         % (", ".join(sorted(missing_events)), mid))
            continue
        if profile_id not in rule.patch_profile_ids or rule.validation is RuleValidation.STALE:
            w.add("stale_patch", e.domain, BLOCKING, mechanics=(mid,), subjects=e.subject_ids,
                  explanation="Rule %s v%s is not established for profile %s."
                              % (mid, rule.version, profile_id),
                  needed="Re-verification of %s on profile %s with evidence." % (mid, profile_id),
                  protocol=protocol)
            continue
        if rule.validation is RuleValidation.CONTRADICTED:
            w.add("conflicting_evidence", e.domain, BLOCKING, mechanics=(mid,),
                  subjects=e.subject_ids,
                  explanation="Accepted evidence for %s disagrees; no value is chosen." % mid,
                  needed="A controlled trial for %s separating the contradicting results." % mid,
                  protocol=protocol)
            continue
        if rule.support is RuleSupport.UNSUPPORTED:
            w.add("missing_implementation", e.domain, BLOCKING, mechanics=(mid,),
                  subjects=e.subject_ids,
                  explanation="%s (%s) is required and no code calculates it. %s"
                              % (mid, e.title, " ".join(rule.limitations)),
                  needed="An implementation of %s owned by %s, with fixture tests and the "
                         "evidence for its parameters." % (mid, rule.owner.value),
                  protocol=protocol)
            continue
        if rule.support is RuleSupport.UNKNOWN:
            w.add("unknown_rule", e.domain, BLOCKING, mechanics=(mid,), subjects=e.subject_ids,
                  explanation="How %s (%s) behaves is not established. %s"
                              % (mid, e.title, " ".join(rule.limitations)),
                  needed="Catalog evidence or a recorded trial establishing %s under the "
                         "scenario's conditions." % e.title,
                  protocol=protocol)
            continue
        if e.critical and not e.is_settled():
            w.add("unvalidated", e.domain, BLOCKING, mechanics=(mid,), subjects=e.subject_ids,
                  explanation="Critical %s rule %s is not checked and reviewed; a low severity "
                              "label cannot make it free." % (e.critical, mid),
                  needed="Reviewed fixture or gameplay evidence for %s." % mid,
                  protocol=protocol)
            continue
        if rule.support is RuleSupport.PARTIAL or rule.validation not in CHECKED:
            if not protocol:
                unvalidated.setdefault(e.domain, []).append(mid)
            else:
                w.add("unvalidated", e.domain, RANKING, mechanics=(mid,), subjects=e.subject_ids,
                      explanation="%s is %s and %s. %s" % (
                          mid, rule.support.value, rule.validation.value, " ".join(rule.limitations)),
                      needed="Fixture or gameplay evidence checking %s." % mid,
                      protocol=protocol)
    for domain, mids in sorted(unvalidated.items()):
        w.add("unvalidated", domain, RANKING, mechanics=tuple(sorted(mids)),
              explanation="Calculated but not checked against evidence: %s." % ", ".join(sorted(mids)),
              needed="For each listed rule, a fixture comparing its output with an independent "
                     "source under stated conditions.")


def _walk_inputs(w, build, inputs):
    """Every required input path of a rule in use must have a value."""
    values = dict(inputs)
    if build.engine is not None:
        values.setdefault("/engine/pob_commit", build.engine.pob_commit)
        values.setdefault("/engine/pob_dirty", build.engine.pob_dirty)
    for mid in w.registry.closure(w.used):
        e = w.registry[mid]
        if set(e.requires_events) - w.scenario.events and not e.critical:
            continue
        missing = [p for p in e.rule.required_input_paths if values.get(p) is None]
        for path in missing:
            if path.startswith("/engine/"):
                continue  # reported once by the engine section
            w.add("missing_data", e.domain, BLOCKING, mechanics=(mid,), subjects=e.subject_ids,
                  fields=(path,),
                  explanation="Input %s required by %s (%s) has no value." % (path, mid, e.title),
                  needed="The value of %s for %s, with its source." % (
                      path, ", ".join(e.subject_ids) or mid),
                  protocol=e.protocol_gap_ids)


def _check_activation(w, groups, rotation):
    for g in groups:
        for sup in g.supports:
            for e in w.registry.for_subject("support:" + sup.skill_id):
                if e.critical != "activation":
                    continue
                gated = [s.skill_id for s in g.active_skills]
                w.used.add(e.mechanic_id)
                if not e.is_settled() or e.satisfied_by is None:
                    w.add("unknown_rule", "activation", BLOCKING, mechanics=(e.mechanic_id,),
                          subjects=tuple("skill:" + s for s in gated),
                          explanation="Reuse condition of %s is unresolved: %s. No repeat use "
                                      "is assumed." % (", ".join(gated), e.title),
                          needed="Evidence of which actions satisfy %s for %s, accepted by a "
                                 "reviewer." % (e.title, ", ".join(gated)),
                          protocol=e.protocol_gap_ids)
                    continue
                if rotation is None:
                    continue
                if not any(s in _rotation_skills(rotation) for s in gated):
                    continue
                actions = set()
                for r in rotation.rules:
                    if r.action.value == "move":
                        actions.add("move")
                    if r.action.value == "use_skill" and r.skill_id:
                        actions.add("skill:" + r.skill_id)
                if not actions & set(e.satisfied_by):
                    w.add("activation_unmet", "activation", BLOCKING,
                          mechanics=(e.mechanic_id,), subjects=tuple("skill:" + s for s in gated),
                          fields=("/rules",),
                          explanation="%s is re-enabled only by %s, and rotation %s has none of "
                                      "those actions; after the first use the skill stays "
                                      "unusable." % (", ".join(gated), ", ".join(e.satisfied_by),
                                                     rotation.rotation_id),
                          needed="A rotation action from %s before each use, with its time "
                                 "counted." % ", ".join(e.satisfied_by))


def _rotation_skills(rotation) -> set[str]:
    return {r.skill_id for r in rotation.rules if r.skill_id}


def _damaging_groups(w, groups, rotation):
    """Groups that can deal damage in this scenario.

    A group whose active skills all need events the scenario lacks is inert.
    A manually used skill (no events, not a buff) deals damage only when the
    rotation uses it; without a rotation every such group counts.
    """
    used = _rotation_skills(rotation) if rotation is not None else None
    out = []
    for g in groups:
        entries = [e for s in g.active_skills
                   for e in w.registry.for_subject("skill:" + s.skill_id)]
        if entries and all(set(e.requires_events) - w.scenario.events for e in entries):
            continue
        manual = entries and all(e.domain != "buff" and not e.requires_events for e in entries)
        if manual and used is not None and not any(s.skill_id in used for s in g.active_skills):
            w.notes.append("group %d (%s) is not used by the rotation; not a damage source"
                           % (g.index, ", ".join(s.skill_id for s in g.active_skills)))
            continue
        out.append(g)
    return out


def _check_attribution(w, groups, rotation):
    rules = [e for e in w.registry.for_subject("scenario:" + w.scenario.scenario_id)
             if e.critical == "attribution"]
    if not rules:
        return
    for rule in rules:
        w.used.add(rule.mechanic_id)
        for g in _damaging_groups(w, groups, rotation):
            for gem in g.active_skills + g.supports:
                prefix = "support:" if gem.support else "skill:"
                for e in w.registry.for_subject(prefix + gem.skill_id):
                    if not e.damage_source:
                        continue
                    if set(e.requires_events) - w.scenario.events:
                        continue
                    source = e.mechanic_id
                    if source not in rule.assignments:
                        w.add("unassigned_damage", "attribution", BLOCKING,
                              mechanics=(rule.mechanic_id, source),
                              subjects=(prefix + gem.skill_id,),
                              explanation="Damage source %s has no ownership class in %s; its "
                                          "damage cannot enter or be excluded from the score."
                                          % (source, rule.mechanic_id),
                              needed="An accepted class (%s) for %s in the attribution rule."
                                     % ("flicker_direct, flicker_secondary or unrelated", source),
                              protocol=rule.protocol_gap_ids)


def _domain_states(registry, rule_ids, findings) -> dict[str, dict[str, str]]:
    domains: dict[str, dict[str, str]] = {}
    for mid in rule_ids:
        e = registry[mid]
        d = domains.setdefault(e.domain, {"coverage": CoverageState.SUPPORTED.value,
                                          "validation": "validated"})
        if e.rule.validation not in CHECKED:
            d["validation"] = "unvalidated"
    for f in findings:
        d = domains.setdefault(f.domain, {"coverage": CoverageState.SUPPORTED.value,
                                          "validation": "validated"})
        if f.severity is BLOCKING:
            d["coverage"] = CoverageState.UNSUPPORTED.value
        elif f.severity is RANKING and d["coverage"] == CoverageState.SUPPORTED.value:
            d["coverage"] = CoverageState.PARTIAL.value
        if f.gap_class != "not_applicable" and f.severity is not INFO:
            d["validation"] = "unvalidated"
    return domains


# ================================================================ decision ===

def decide(report: CoverageReport, registry: MechanicsRegistry) -> Decision:
    """Whether a score computed under this coverage may count.

    Blocks on every blocking finding and open blocking protocol gap, and on
    every activation or attribution rule in the report's closure that is not
    settled, whatever severity any gap carries.
    """
    blocking = [f.gap_id for f in report.findings if f.severity is BLOCKING]
    blocking += [g.gap_id for g in report.protocol_gaps
                 if g.status is GapStatus.OPEN and g.severity is GapSeverity.BLOCKING]
    unsettled = []
    for mid in report.critical_rule_ids:
        if mid not in registry or not registry[mid].is_settled():
            unsettled.append(mid)
    for kind in ("activation", "attribution"):
        for e in registry.critical(kind):
            if e.mechanic_id in report.critical_rule_ids:
                continue
            if any(s == "scenario:" + report.scenario_id for s in e.subject_ids):
                unsettled.append(e.mechanic_id)
    if registry.registry_hash() != report.registry_hash:
        reasons = ("report was produced under registry %s; current is %s"
                   % (report.registry_hash[:12], registry.registry_hash()[:12]),)
        return Decision(False, tuple(sorted(set(blocking))), tuple(sorted(set(unsettled))), reasons)
    reasons = []
    if blocking:
        reasons.append("%d blocking gaps open" % len(set(blocking)))
    if unsettled:
        reasons.append("critical rules not settled: %s" % ", ".join(sorted(set(unsettled))))
    return Decision(eligible=not blocking and not unsettled,
                    blocking_gap_ids=tuple(sorted(set(blocking))),
                    unsettled_critical=tuple(sorted(set(unsettled))),
                    reasons=tuple(reasons))
