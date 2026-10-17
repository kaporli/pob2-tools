"""Does this engine still describe the live patch? (P02-T02)

A version label is not an answer. The question is settled by replaying a
fixed fixture set against the exported catalog and, where the fixture is
about behaviour, against the engine itself, and then by comparing what the
engine's data release can possibly cover against the patch the official
release evidence names.

``verified`` is deliberately hard to reach. It needs every fixture to match,
a byte-exact capture of the official release page, an engine release no older
than that patch, a clean checkout and no blocking gap. Anything short of that
is ``partial`` or ``unknown``; ``stale`` is reserved for a profile that was
pinned to a patch which is no longer live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..domain.enums import Compatibility
from ..domain.records import CatalogEntity

FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "compatibility.json"

MATCH = "match"
MISMATCH = "mismatch"
ABSENT = "absent"
UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class FixtureOutcome:
    fixture_id: str
    kind: str
    outcome: str
    detail: str
    expected: Any = None
    observed: Any = None

    def to_dict(self) -> dict:
        return {"fixture_id": self.fixture_id, "kind": self.kind,
                "outcome": self.outcome, "detail": self.detail,
                "expected": self.expected, "observed": self.observed}


@dataclass
class CompatibilityReport:
    compatibility: Compatibility
    reasons: list[str]
    outcomes: list[FixtureOutcome] = field(default_factory=list)
    fixture_set_version: int = 0
    recorded_from: dict = field(default_factory=dict)

    @property
    def matched(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.outcome == MATCH)

    def to_dict(self) -> dict:
        return {
            "compatibility": self.compatibility.value,
            "reasons": list(self.reasons),
            "fixture_set_version": self.fixture_set_version,
            "recorded_from": dict(self.recorded_from),
            "counts": {state: sum(1 for o in self.outcomes if o.outcome == state)
                       for state in (MATCH, MISMATCH, ABSENT, UNCHECKED)},
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }


def compatibility_fixtures(path: str | Path = FIXTURE_FILE) -> dict:
    """The fixed fixture set. Shipped with the package, never generated here."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _lookup(entities: Mapping[str, Sequence[CatalogEntity]], table: str,
            entity_id: str) -> CatalogEntity | None:
    for entity in entities.get(table, ()):
        if entity.entity_id == entity_id:
            return entity
    return None


def _dig(value: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(value, Mapping):
            value = value.get(part)
        elif isinstance(value, (list, tuple)):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return value


def run_fixtures(fixtures: Mapping[str, Any],
                 entities: Mapping[str, Sequence[CatalogEntity]],
                 *, behaviour: Callable[[Mapping[str, Any]], Mapping[str, Any]]
                 | None = None) -> list[FixtureOutcome]:
    """Replay the fixture set. A fixture that cannot run is ``unchecked``.

    ``behaviour`` loads a build document and returns engine stat values. It
    is optional: without an engine the behaviour fixtures are reported as
    unchecked, which is not a pass and makes the profile ``unknown``.
    """
    outcomes: list[FixtureOutcome] = []
    for fixture in fixtures.get("fixtures") or ():
        kind = fixture.get("kind")
        if kind == "availability":
            outcomes.append(_availability(fixture, entities))
        elif kind == "field":
            outcomes.append(_field(fixture, entities))
        elif kind == "count":
            outcomes.append(_count(fixture, entities))
        elif kind == "members":
            outcomes.append(_members(fixture, entities))
        elif kind == "behaviour":
            outcomes.append(_behaviour(fixture, behaviour))
        else:
            outcomes.append(FixtureOutcome(
                fixture.get("fixture_id", "?"), str(kind), UNCHECKED,
                "unknown fixture kind %r" % kind))
    return outcomes


def _availability(fixture: Mapping[str, Any],
                  entities: Mapping[str, Sequence[CatalogEntity]]) -> FixtureOutcome:
    table, wanted = fixture["table"], fixture["entity_id"]
    entity = _lookup(entities, table, wanted)
    if entity is None:
        return FixtureOutcome(fixture["fixture_id"], "availability", ABSENT,
                              "%s is not in table %s" % (wanted, table),
                              expected=wanted)
    name = fixture.get("display_name")
    if name is not None and name not in entity.display_names:
        return FixtureOutcome(
            fixture["fixture_id"], "availability", MISMATCH,
            "%s is present but its display names are %s"
            % (wanted, ", ".join(entity.display_names) or "empty"),
            expected=name, observed=list(entity.display_names))
    return FixtureOutcome(fixture["fixture_id"], "availability", MATCH,
                          "%s present in %s" % (wanted, table), expected=wanted,
                          observed=wanted)


def _field(fixture: Mapping[str, Any],
           entities: Mapping[str, Sequence[CatalogEntity]]) -> FixtureOutcome:
    table, wanted = fixture["table"], fixture["entity_id"]
    entity = _lookup(entities, table, wanted)
    if entity is None:
        return FixtureOutcome(fixture["fixture_id"], "field", ABSENT,
                              "%s is not in table %s" % (wanted, table),
                              expected=fixture.get("expected"))
    observed = _dig(entity.raw_reference, fixture["path"])
    expected = fixture.get("expected")
    if observed != expected:
        return FixtureOutcome(
            fixture["fixture_id"], "field", MISMATCH,
            "%s.%s is %r, recorded as %r"
            % (wanted, fixture["path"], observed, expected),
            expected=expected, observed=observed)
    return FixtureOutcome(fixture["fixture_id"], "field", MATCH,
                          "%s.%s unchanged" % (wanted, fixture["path"]),
                          expected=expected, observed=observed)


def _members(fixture: Mapping[str, Any],
             entities: Mapping[str, Sequence[CatalogEntity]]) -> FixtureOutcome:
    """A list field still holds every ``includes`` and no ``excludes`` entry.

    Entries outside both lists are ignored, so upstream adding an unrelated
    value is not a mismatch; one moving to the wrong side is.
    """
    table, wanted = fixture["table"], fixture["entity_id"]
    entity = _lookup(entities, table, wanted)
    if entity is None:
        return FixtureOutcome(fixture["fixture_id"], "members", ABSENT,
                              "%s is not in table %s" % (wanted, table))
    observed = _dig(entity.raw_reference, fixture["path"])
    if not isinstance(observed, (list, tuple)):
        return FixtureOutcome(fixture["fixture_id"], "members", MISMATCH,
                              "%s.%s is %r, not a list"
                              % (wanted, fixture["path"], observed))
    present = set(observed)
    lost = sorted(set(fixture.get("includes") or ()) - present)
    gained = sorted(set(fixture.get("excludes") or ()) & present)
    expected = {"includes": len(fixture.get("includes") or ()),
                "excludes": len(fixture.get("excludes") or ())}
    if lost or gained:
        return FixtureOutcome(
            fixture["fixture_id"], "members", MISMATCH,
            "%s.%s lost %s; gained excluded %s"
            % (wanted, fixture["path"], ", ".join(lost) or "nothing",
               ", ".join(gained) or "nothing"),
            expected=expected, observed={"lost": lost, "gained": gained})
    return FixtureOutcome(fixture["fixture_id"], "members", MATCH,
                          "%s.%s holds all %d included and none of %d excluded"
                          % (wanted, fixture["path"], expected["includes"],
                             expected["excludes"]),
                          expected=expected, observed=len(observed))


def _count(fixture: Mapping[str, Any],
           entities: Mapping[str, Sequence[CatalogEntity]]) -> FixtureOutcome:
    table = fixture["table"]
    observed = len(entities.get(table, ()))
    minimum = int(fixture.get("minimum", 0))
    if observed < minimum:
        return FixtureOutcome(
            fixture["fixture_id"], "count", MISMATCH,
            "table %s holds %d entities, below the recorded floor of %d"
            % (table, observed, minimum), expected=minimum, observed=observed)
    return FixtureOutcome(fixture["fixture_id"], "count", MATCH,
                          "table %s holds %d entities" % (table, observed),
                          expected=minimum, observed=observed)


def _behaviour(fixture: Mapping[str, Any],
               behaviour: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None
               ) -> FixtureOutcome:
    if behaviour is None:
        return FixtureOutcome(
            fixture["fixture_id"], "behaviour", UNCHECKED,
            "no engine was available, so this behaviour was not checked")
    try:
        values = behaviour(fixture)
    except Exception as exc:  # the engine failed; that is an answer, not a pass
        return FixtureOutcome(
            fixture["fixture_id"], "behaviour", MISMATCH,
            "the engine could not run this fixture: %s: %s"
            % (type(exc).__name__, exc))
    expected = fixture.get("expected") or {}
    tolerance = float(fixture.get("relative_tolerance", 1e-6))
    mismatches = []
    observed = {}
    for key, want in expected.items():
        got = values.get(key)
        observed[key] = got
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            scale = max(abs(float(want)), 1e-9)
            if abs(float(got) - float(want)) / scale > tolerance:
                mismatches.append("%s: %r, recorded %r" % (key, got, want))
        elif got != want:
            mismatches.append("%s: %r, recorded %r" % (key, got, want))
    if mismatches:
        return FixtureOutcome(fixture["fixture_id"], "behaviour", MISMATCH,
                              "; ".join(mismatches), expected=dict(expected),
                              observed=observed)
    return FixtureOutcome(fixture["fixture_id"], "behaviour", MATCH,
                          "%d value(s) within %g relative tolerance"
                          % (len(expected), tolerance),
                          expected=dict(expected), observed=observed)


def decide_compatibility(outcomes: Sequence[FixtureOutcome], *,
                         patch_id: str | None,
                         patch_published_at: str | None,
                         engine_released_at: str | None,
                         evidence_is_verbatim: bool,
                         checkout_is_pinned: bool,
                         blocking_gap_ids: Sequence[str] = (),
                         pinned_patch_id: str | None = None
                         ) -> tuple[Compatibility, list[str]]:
    """Decide the profile's compatibility, worst condition first.

    ``pinned_patch_id`` is for a profile that was pinned to an earlier patch:
    it stays usable as a historical profile and is labelled ``stale`` rather
    than being re-judged against a patch it never claimed.
    """
    reasons: list[str] = []
    if patch_id is None:
        reasons.append(
            "no official release evidence resolved a current patch id")
        return Compatibility.UNKNOWN, reasons
    # Checked before the fixture outcomes: a profile pinned to a patch that
    # is no longer live is stale whatever the fixtures say, and relabelling
    # it on a fixture result would hide what it actually is.
    if pinned_patch_id is not None and pinned_patch_id != patch_id:
        reasons.append(
            "this profile is pinned to patch %s and the live patch is %s; it "
            "remains usable as a historical profile for %s"
            % (pinned_patch_id, patch_id, pinned_patch_id))
        return Compatibility.STALE, reasons

    if not outcomes:
        reasons.append("the compatibility fixture set produced no outcomes")
        return Compatibility.UNKNOWN, reasons
    unchecked = [o.fixture_id for o in outcomes if o.outcome == UNCHECKED]
    if unchecked:
        reasons.append("fixtures not checked: %s" % ", ".join(sorted(unchecked)))
        return Compatibility.UNKNOWN, reasons

    failed = [o for o in outcomes if o.outcome in (MISMATCH, ABSENT)]
    if failed:
        reasons.append("%d fixture(s) did not match: %s"
                       % (len(failed),
                          ", ".join(sorted(o.fixture_id for o in failed))))
    if engine_released_at is None:
        reasons.append("the engine's own release date could not be read, so "
                       "whether its data can cover %s is unknown" % patch_id)
    elif patch_published_at and engine_released_at < patch_published_at:
        reasons.append(
            "the engine data release (%s) predates patch %s (%s), so content "
            "introduced by that patch is not in this catalog"
            % (engine_released_at[:10], patch_id, patch_published_at[:10]))
    if not evidence_is_verbatim:
        reasons.append("the release evidence is a summary, not a byte-exact "
                       "capture of the official page")
    if not checkout_is_pinned:
        reasons.append("the running checkout is not a clean pinned tree")
    if blocking_gap_ids:
        reasons.append("blocking gaps remain open: %s"
                       % ", ".join(sorted(blocking_gap_ids)))
    if reasons:
        return Compatibility.PARTIAL, reasons
    reasons.append("every fixture matched, the engine release covers patch %s, "
                   "the release evidence is a verbatim capture and the "
                   "checkout is pinned" % patch_id)
    return Compatibility.VERIFIED, reasons
