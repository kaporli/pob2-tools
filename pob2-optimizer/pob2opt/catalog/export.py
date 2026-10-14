"""`catalog export`: a versioned catalog and patch profile (P02-T02).

One pass produces a self-contained bundle: the ``GameCatalog``, the
``PatchProfile`` that pins it, every ``DataGap`` the rules could not close,
and a ``SourceDocument`` plus payload for every piece of evidence either
cites. Every reference inside the bundle resolves inside the bundle, which
is what contracts.md asks of an export.

The export refuses three things. It never invents a patch id: no release
evidence means ``unknown`` and a gap. It never reports ``verified`` on a
version label. And it never writes a profile whose level range or point
maximums it could not source; that is an exit-3 failure naming the pattern
that stopped matching.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from ..domain.enums import GapKind, GapSeverity, Redistribution
from ..domain.identity import document_hash
from ..domain.records import (SCHEMA_VERSION, CatalogEntity, DataGap,
                              GameCatalog, PatchProfile, SourceDocument)
from ..domain.validation import RecordIndex, validate_record
from ..evaluation import protocol
from . import compatibility as compat
from .compatibility import CompatibilityReport, decide_compatibility, run_fixtures
from .entities import (CATALOG_TABLE_ORDER, catalog_hash, derive_passive_edges,
                       entities_from_rows)
from .evidence import EvidenceBundle, json_payload, pob_source_url
from .reader import CatalogReader
from .release import ReleaseCapture, release_evidence_document, current_release
from .rules import GAP_PREFIX, build_character_rules, make_gap
from .sources import Citation, citations_to_payload

#: Bumped when the export changes what it reads or how it labels it.
EXPORTER_VERSION = "p02-t02.1"

#: Tables read straight from the engine. The other two are derived:
#: ``ascendancies`` from the class rows and ``passive_edges`` from the node
#: rows, so neither costs a second read.
ENGINE_TABLES = tuple(protocol.CATALOG_HANDLERS)


@dataclass(frozen=True, slots=True)
class ExportRequest:
    """The ``--profile FILE`` input.

    ``pinned_patch_id`` makes this a re-check of a profile that was pinned to
    an earlier patch: it stays usable as a historical profile and is labelled
    ``stale`` rather than judged against a patch it never claimed.
    """

    game: str = "poe2"
    realm: str = "poe2"
    league_id: str = "Standard"
    pob_root: str | None = None
    release_evidence_dir: str | None = None
    pinned_patch_id: str | None = None
    label: str | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "ExportRequest":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("%s is not a JSON object" % path)
        version = raw.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(
                "catalog profile request declares schema_version %r; this "
                "build reads %d" % (version, SCHEMA_VERSION))
        known = {f for f in cls.__slots__}
        unknown = sorted(set(raw) - known - {"schema_version"})
        if unknown:
            raise ValueError("unknown request keys: %s" % ", ".join(unknown))
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class CatalogExport:
    """Everything one export produced."""

    catalog: GameCatalog
    profile: PatchProfile
    gaps: list[DataGap]
    evidence: list[SourceDocument]
    blobs: dict[str, bytes]
    report: CompatibilityReport
    acquisition: Any = None
    resolutions: dict[str, Any] = field(default_factory=dict)
    reader: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def records(self) -> list[Any]:
        root = [self.acquisition] if self.acquisition is not None else []
        return [*root, *self.evidence, *self.gaps, self.catalog, self.profile]

    def summary(self) -> dict:
        return {
            "exporter_version": EXPORTER_VERSION,
            "catalog_hash": self.catalog.catalog_hash,
            "patch_profile_id": self.profile.record_id,
            "patch_id": self.profile.patch_id,
            "league_id": self.profile.league_id,
            "pob_commit": self.profile.pob_commit,
            "pob_dirty_hash": self.profile.pob_dirty_hash,
            "adapter_version": self.profile.adapter_version,
            "compatibility": self.profile.compatibility.value,
            "entity_counts": {table: len(self.catalog.entities.get(table, ()))
                              for table in CATALOG_TABLE_ORDER},
            "gap_ids": [gap.gap_id for gap in self.gaps],
            "evidence_ids": [doc.record_id for doc in self.evidence],
            "compatibility_report": self.report.to_dict(),
            "resolutions": self.resolutions,
            "reader": self.reader,
            "validation_errors": list(self.validation_errors),
        }


class CatalogProvider(Protocol):
    def export(self, profile: ExportRequest) -> CatalogExport:
        ...  # pragma: no cover - protocol


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _engine_release(citation: Citation | None) -> tuple[str | None, str | None]:
    """(version, ISO date) of the engine's own release, or (None, None)."""
    if citation is None or len(citation.values) < 4:
        return None, None
    version, year, month, day = citation.values[:4]
    return version, "%s-%s-%sT00:00:00Z" % (year, month, day)


class PobCatalogProvider:
    """Reads one catalog out of a pinned engine and pins a profile to it."""

    def __init__(self, reader: CatalogReader, *,
                 citations: Mapping[str, Citation],
                 release_captures: Sequence[ReleaseCapture] = (),
                 pob_commit: str | None = None,
                 pob_dirty_hash: str | None = None,
                 adapter_version: str = protocol.ADAPTER_VERSION,
                 behaviour: Callable[[Mapping[str, Any]], Mapping[str, Any]]
                 | None = None,
                 fixtures: Mapping[str, Any] | None = None,
                 clock: Callable[[], str] = _now) -> None:
        self.reader = reader
        self.citations = dict(citations)
        self.release_captures = list(release_captures)
        self.pob_commit = pob_commit
        self.pob_dirty_hash = pob_dirty_hash
        self.adapter_version = adapter_version
        self.behaviour = behaviour
        self.fixtures = (dict(fixtures) if fixtures is not None
                         else compat.compatibility_fixtures())
        self.clock = clock

    # -- the one public operation ----------------------------------------

    def export(self, profile: ExportRequest) -> CatalogExport:
        created_at = self.clock()
        evidence = EvidenceBundle(acquisition_version=EXPORTER_VERSION,
                                  created_at=created_at)
        reader_description = self.reader.describe()
        acquisition = evidence.root_records(
            invocation_id="evidence/export/invocation",
            provider="pob2opt",
            source_ref=str(reader_description.get("pob_root")
                           or reader_description.get("source") or "unknown"),
            payload=json_payload({
                "exporter_version": EXPORTER_VERSION,
                "adapter_version": self.adapter_version,
                "requested": {"game": profile.game, "realm": profile.realm,
                              "league_id": profile.league_id,
                              "pinned_patch_id": profile.pinned_patch_id,
                              "label": profile.label},
                "reader": reader_description,
                "release_captures": [capture.source_url
                                     for capture in self.release_captures],
            }))

        entities = self._read_entities()
        digest = catalog_hash(entities)
        rule_sources = self.reader.rule_sources()

        citation_evidence = evidence.add(
            "evidence/pob/source/citations",
            json_payload(citations_to_payload(self.citations)),
            provider="path-of-building-poe2",
            source_url=pob_source_url(self.pob_commit, "src"),
            media_type="application/json")

        rule_build = build_character_rules(
            rule_sources=rule_sources,
            classes=entities.get("classes", []),
            ascendancies=entities.get("ascendancies", []),
            slots=entities.get("slots", []),
            gems=entities.get("gems", []),
            citations=self.citations,
            evidence=evidence,
            pob_commit=self.pob_commit,
            created_at=created_at)
        gaps = list(rule_build.gaps)

        capture, release_problem = current_release(
            self.release_captures, profile.game, profile.realm)
        live_patch_id, patch_published_at, patch_evidence_ids = (
            self._resolve_patch(evidence, gaps, created_at, capture, release_problem))
        # A pinned profile keeps the patch it was pinned to. It is not
        # re-labelled as describing the live patch just because a newer one
        # was captured; it stays usable as a historical profile.
        patch_id = profile.pinned_patch_id or live_patch_id
        if profile.pinned_patch_id is not None:
            gaps.extend(self._historical_gaps(profile.pinned_patch_id,
                                              live_patch_id, created_at))

        engine_version, engine_released_at = _engine_release(
            self.citations.get("engine_release"))
        outcomes = run_fixtures(self.fixtures, entities,
                                behaviour=self.behaviour)
        checkout_is_pinned = bool(self.pob_commit) and self.pob_dirty_hash is None
        blocking = [gap.gap_id for gap in gaps
                    if gap.severity is GapSeverity.BLOCKING]
        verdict, reasons = decide_compatibility(
            outcomes,
            patch_id=live_patch_id,
            patch_published_at=patch_published_at,
            engine_released_at=engine_released_at,
            evidence_is_verbatim=bool(capture and capture.is_verbatim),
            checkout_is_pinned=checkout_is_pinned,
            blocking_gap_ids=blocking,
            pinned_patch_id=profile.pinned_patch_id)
        report = CompatibilityReport(
            compatibility=verdict, reasons=reasons, outcomes=outcomes,
            fixture_set_version=int(self.fixtures.get("fixture_set_version", 0)),
            recorded_from=dict(self.fixtures.get("recorded_from") or {}))

        compatibility_evidence = evidence.add(
            "evidence/export/compatibility",
            json_payload({
                "exporter_version": EXPORTER_VERSION,
                "adapter_version": self.adapter_version,
                "engine_release_version": engine_version,
                "engine_released_at": engine_released_at,
                "pob_commit": self.pob_commit,
                "pob_dirty_hash": self.pob_dirty_hash,
                "reader": reader_description,
                "report": report.to_dict(),
            }),
            provider="pob2opt",
            source_url=None,
            media_type="application/json",
            redistribution=Redistribution.ALLOWED)

        gaps.extend(self._compatibility_gaps(
            report, created_at, engine_released_at, live_patch_id,
            patch_published_at, capture, checkout_is_pinned))

        profile_record = PatchProfile(
            schema_version=SCHEMA_VERSION,
            record_id="patch-profile/%s/%s" % (patch_id or "unknown-patch",
                                               digest[:16]),
            created_at=created_at,
            provenance_ids=[citation_evidence, compatibility_evidence],
            game=profile.game,
            realm=profile.realm,
            league_id=profile.league_id,
            patch_id=patch_id or "unknown",
            patch_evidence_ids=patch_evidence_ids,
            resolved_at=created_at,
            pob_commit=self.pob_commit or "unknown",
            pob_dirty_hash=self.pob_dirty_hash,
            catalog_hash=digest,
            adapter_version=self.adapter_version,
            compatibility=verdict,
            compatibility_evidence_ids=[compatibility_evidence],
            character_rules=_with_gap_ids(rule_build.rules, gaps))

        catalog_evidence = evidence.add(
            "evidence/export/catalog-read",
            json_payload({"reader": reader_description,
                          "tables": {table: len(entities.get(table, ()))
                                     for table in CATALOG_TABLE_ORDER},
                          "catalog_hash": digest}),
            provider="pob2opt",
            source_url=None,
            media_type="application/json",
            redistribution=Redistribution.ALLOWED)

        catalog_record = GameCatalog(
            schema_version=SCHEMA_VERSION,
            record_id="game-catalog/%s" % digest[:16],
            created_at=created_at,
            provenance_ids=[catalog_evidence],
            catalog_hash=digest,
            patch_profile_id=profile_record.record_id,
            entities=entities,
            source_evidence_ids=[catalog_evidence, citation_evidence])

        export = CatalogExport(
            catalog=catalog_record, profile=profile_record, gaps=gaps,
            evidence=evidence.documents, blobs=evidence.payloads,
            report=report, reader=reader_description,
            acquisition=acquisition)
        export.validation_errors = _validate_bundle(export)
        return export

    # -- parts -------------------------------------------------------------

    def _read_entities(self) -> dict[str, list[CatalogEntity]]:
        entities: dict[str, list[CatalogEntity]] = {}
        class_rows: list[dict] = []
        node_rows: list[dict] = []
        for table in ENGINE_TABLES:
            rows = self.reader.rows(table)
            if table == "classes":
                class_rows = rows
            if table == "passive_nodes":
                node_rows = rows
            entities[table] = entities_from_rows(table, rows)
        entities["ascendancies"] = entities_from_rows("ascendancies", class_rows)
        entities["passive_edges"] = derive_passive_edges(node_rows)
        return {table: entities.get(table, []) for table in CATALOG_TABLE_ORDER}

    def _resolve_patch(self, evidence: EvidenceBundle, gaps: list[DataGap],
                       created_at: str, selected: ReleaseCapture | None,
                       problem: str | None) -> tuple[str | None, str | None, list[str]]:
        ids = []
        for capture in self.release_captures:
            document, payload = release_evidence_document(
                capture,
                record_id="evidence/release/%s/%s" % (
                    capture.patch_id, document_hash(capture.payload())[:16]),
                created_at=created_at, acquisition_version=EXPORTER_VERSION)
            if document.record_id in ids:
                continue
            evidence_id = evidence.adopt(document, payload)
            ids.append(evidence_id)
        if selected is None:
            gaps.append(make_gap(
                "%s/current-patch-unresolved" % GAP_PREFIX,
                kind=GapKind.MISSING_INPUT,
                severity=GapSeverity.BLOCKING,
                explanation=problem or "Current patch could not be resolved.",
                needed_evidence=(
                    "a capture of the official Path of Exile 2 patch notes "
                    "page for the live patch, carrying the thread URL, the "
                    "patch version in its title and its publication date"),
                collection_method="import request",
                created_at=created_at,
                field_paths=["/patch_id", "/patch_evidence_ids"]))
            return None, None, ids
        return selected.patch_id, selected.patch_published_at, ids

    def _historical_gaps(self, pinned: str, live: str | None,
                         created_at: str) -> list[DataGap]:
        """What a profile pinned to an earlier patch is still missing."""
        gaps: list[DataGap] = []
        if not any(capture.patch_id == pinned
                   for capture in self.release_captures):
            gaps.append(make_gap(
                "%s/historical-patch-evidence-missing" % GAP_PREFIX,
                kind=GapKind.MISSING_INPUT,
                severity=GapSeverity.INFORMATIONAL,
                explanation=(
                    "This profile is pinned to patch %s and no release capture "
                    "for that patch was supplied, so its publication date is "
                    "unknown. The profile is still usable as a historical "
                    "profile for %s; it just cannot say when %s went live."
                    % (pinned, pinned, pinned)),
                needed_evidence=(
                    "a capture of the official patch notes page for patch %s, "
                    "carrying its thread URL and publication date" % pinned),
                collection_method="import request",
                created_at=created_at,
                field_paths=["/patch_evidence_ids"]))
        if live is not None and live != pinned:
            gaps.append(make_gap(
                "%s/pinned-patch-superseded" % GAP_PREFIX,
                kind=GapKind.STALE_PATCH,
                severity=GapSeverity.INFORMATIONAL,
                explanation=(
                    "Patch %s is live and this profile is pinned to %s. The "
                    "profile remains valid for results already produced under "
                    "%s; it must not be used to describe the live game."
                    % (live, pinned, pinned)),
                needed_evidence=(
                    "a fresh export against patch %s, and a decision on "
                    "whether results produced under %s are still comparable"
                    % (live, pinned)),
                collection_method="engine implementation",
                created_at=created_at,
                field_paths=["/patch_id", "/compatibility"]))
        return gaps

    def _compatibility_gaps(self, report: CompatibilityReport, created_at: str,
                            engine_released_at: str | None,
                            patch_id: str | None, patch_published_at: str | None,
                            capture: ReleaseCapture | None,
                            checkout_is_pinned: bool) -> list[DataGap]:
        gaps: list[DataGap] = []
        failed = [outcome for outcome in report.outcomes
                  if outcome.outcome in (compat.MISMATCH, compat.ABSENT)]
        if failed:
            gaps.append(make_gap(
                "%s/compatibility-fixtures-failed" % GAP_PREFIX,
                kind=GapKind.CONFLICTING_EVIDENCE,
                severity=GapSeverity.RANKING_SENSITIVE,
                explanation=(
                    "%d compatibility fixture(s) did not match this catalog: "
                    "%s. Each one was recorded from a checkout that produced a "
                    "different answer, so something the optimizer depends on "
                    "has moved."
                    % (len(failed), "; ".join("%s (%s)" % (o.fixture_id, o.detail)
                                              for o in failed))),
                needed_evidence=(
                    "for each named fixture, the current upstream value and "
                    "the change that moved it, read from the engine changelog "
                    "and the official patch notes for the resolved patch"),
                collection_method="source lookup",
                created_at=created_at,
                field_paths=["/compatibility"]))
        if (patch_published_at and engine_released_at
                and engine_released_at < patch_published_at):
            gaps.append(make_gap(
                "%s/catalog-predates-current-patch" % GAP_PREFIX,
                kind=GapKind.STALE_PATCH,
                severity=GapSeverity.RANKING_SENSITIVE,
                explanation=(
                    "The engine data release is dated %s and patch %s was "
                    "published %s, so any entity, skill or modifier that patch "
                    "introduced is absent from this catalog. The export cannot "
                    "list what is missing, only that something is."
                    % (engine_released_at[:10], patch_id,
                       patch_published_at[:10])),
                needed_evidence=(
                    "the official patch notes for every patch published after "
                    "%s, listing added or changed classes, ascendancies, "
                    "skills, support gems and item bases, and a Path of "
                    "Building release that includes them"
                    % engine_released_at[:10]),
                collection_method="source lookup",
                created_at=created_at,
                field_paths=["/catalog_hash", "/compatibility"]))
        if capture is not None and not capture.is_verbatim:
            gaps.append(make_gap(
                "%s/release-evidence-not-verbatim" % GAP_PREFIX,
                kind=GapKind.MISSING_INPUT,
                severity=GapSeverity.INFORMATIONAL,
                explanation=(
                    "The release evidence for patch %s is a %s capture made by "
                    "%s, not a byte-exact copy of the official page. It is "
                    "enough to name the patch and never enough to certify "
                    "compatibility." % (patch_id, capture.fidelity,
                                        capture.capture_method)),
                needed_evidence=(
                    "a byte-exact capture of %s, stored with its retrieval "
                    "timestamp and content hash" % capture.source_url),
                collection_method="import request",
                created_at=created_at,
                field_paths=["/patch_evidence_ids"]))
        if not checkout_is_pinned:
            gaps.append(make_gap(
                "%s/unpinned-checkout" % GAP_PREFIX,
                kind=GapKind.MISSING_INPUT,
                severity=GapSeverity.INFORMATIONAL,
                explanation=(
                    "The engine checkout this catalog was read from is not a "
                    "clean pinned tree (commit %s, working-tree digest %s), so "
                    "the catalog cannot be reproduced from the commit alone."
                    % (self.pob_commit or "unknown",
                       self.pob_dirty_hash or "none")),
                needed_evidence=(
                    "a clean checkout of the pinned Path of Building commit "
                    "with no local modifications, and a re-export whose "
                    "catalog hash matches this one"),
                collection_method="engine implementation",
                created_at=created_at,
                field_paths=["/pob_dirty_hash"]))
        return gaps


def _with_gap_ids(rules, gaps: Sequence[DataGap]):
    import dataclasses
    return dataclasses.replace(
        rules, missing_rule_gap_ids=sorted({gap.gap_id for gap in gaps}))


def _validate_bundle(export: CatalogExport) -> list[str]:
    """Every record validated against an index of the bundle itself.

    contracts.md requires cross-record references to resolve inside the
    export. Running it here means a malformed bundle is reported by the
    command that produced it rather than by whoever reads it next.
    """
    index = RecordIndex()
    for record in export.records:
        index.add(record)
    for digest in export.blobs:
        index.blob_hashes.add(digest)
    problems: list[str] = []
    for record in export.records:
        report = validate_record(record, index=index)
        for error in report.errors:
            problems.append("%s %s [%s]: %s" % (
                getattr(record, "record_id", "?"), error.field_path,
                error.code, error.message))
    return problems


# ----------------------------------------------------------------- output ---

def write_bundle(export: CatalogExport, out_dir: str | Path) -> dict[str, str]:
    """Write the bundle. Returns the paths written, relative to ``out_dir``."""
    from ..domain.codec import to_jsonable

    out = Path(out_dir)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    (out / "blobs").mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def dump(relative: str, value: Any) -> None:
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=1, sort_keys=True,
                                   ensure_ascii=False) + "\n",
                        encoding="utf-8")
        written[relative] = str(path)

    dump("catalog.json", to_jsonable(export.catalog))
    dump("patch_profile.json", to_jsonable(export.profile))
    if export.acquisition is not None:
        # The bundle's root: gaps and evidence cite it, so a corpus importing
        # the bundle needs it to resolve their provenance.
        dump("acquisition.json", to_jsonable(export.acquisition))
    dump("gaps.json", [to_jsonable(gap) for gap in export.gaps])
    for document in export.evidence:
        dump("evidence/%s.json" % document.record_id.replace("/", "_"),
             to_jsonable(document))
    for digest, payload in export.blobs.items():
        path = out / "blobs" / digest
        path.write_bytes(payload)
        written["blobs/%s" % digest] = str(path)
    dump("export.json", export.summary())
    return written
