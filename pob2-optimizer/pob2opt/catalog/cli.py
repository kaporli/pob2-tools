"""`pob2opt catalog export --profile FILE --out DIR` (P02-T02).

JSON goes to stdout, prose to stderr, as interfaces.md requires. Exit codes
are the shared ones: 2 for an unreadable request, 3 when the engine or a
rule source needed to produce the profile is missing, 4 when the bundle it
produced does not validate.

Two sources of rows are supported. ``--pob-root`` reads them from a live
engine through the P02-T01 adapter and can save them with ``--capture-rows``.
``--rows FILE`` replays such a capture, which is how the offline lane
exercises the same export code with no PoB and no network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_MISSING_DEPENDENCY = 3
EXIT_INTERNAL = 4

#: Timeouts for the catalog reads. A page is milliseconds on the pinned
#: checkout; the boot is the slow part and has its own allowance.
READ_TIMEOUT_S = 300.0
START_TIMEOUT_S = 600.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt catalog export",
        description="Export pinned PoB entities and compatibility evidence.")
    parser.add_argument("--profile", required=True,
                        help="catalog profile request file")
    parser.add_argument("--out", required=True, help="output bundle directory")
    parser.add_argument("--pob-root", default=None,
                        help="PoB checkout; defaults to the request, then POB2_ROOT")
    parser.add_argument("--release-evidence", default=None,
                        help="directory of official release capture files")
    parser.add_argument("--rows", default=None,
                        help="replay a saved row capture instead of reading an engine")
    parser.add_argument("--capture-rows", default=None,
                        help="write the engine rows to this file while exporting")
    parser.add_argument("--resolve-build", action="append", default=[],
                        help="resolve a build document against the export; repeatable")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[2:] if argv is None else argv))
    try:
        return _run(args)
    except _Refused as refused:
        print(refused.message, file=sys.stderr)
        return refused.code


class _Refused(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _run(args) -> int:
    from .export import (EXPORTER_VERSION, ExportRequest, PobCatalogProvider,
                         write_bundle)
    from .release import ReleaseCaptureError, load_release_captures
    from .resolve import resolve_build_document
    from .rules import MissingRuleSource

    try:
        request = ExportRequest.from_file(args.profile)
    except (OSError, ValueError) as exc:
        raise _Refused(EXIT_INVALID_REQUEST,
                       "catalog profile request %s is not usable: %s"
                       % (args.profile, exc)) from None

    evidence_dir = (args.release_evidence or request.release_evidence_dir)
    captures = []
    if evidence_dir:
        try:
            captures = load_release_captures(evidence_dir)
        except ReleaseCaptureError as exc:
            raise _Refused(EXIT_INVALID_REQUEST, str(exc)) from None
        if not captures:
            print("no release captures in %s; the patch will be unknown"
                  % evidence_dir, file=sys.stderr)
    else:
        print("no release evidence directory given; the patch will be unknown",
              file=sys.stderr)

    out_dir = Path(args.out).resolve()
    if args.rows:
        provider, closer = _replay_provider(args, request, captures)
    else:
        provider, closer = _engine_provider(args, request, captures)

    try:
        try:
            export = provider.export(request)
        except MissingRuleSource as exc:
            raise _Refused(EXIT_MISSING_DEPENDENCY, str(exc)) from None
        for path in args.resolve_build:
            try:
                xml = Path(path).read_text(encoding="utf-8")
            except OSError as exc:
                raise _Refused(EXIT_INVALID_REQUEST,
                               "build document %s is unreadable: %s"
                               % (path, exc)) from None
            export.resolutions[os.path.basename(path)] = resolve_build_document(
                xml, export.catalog.entities).to_dict()
    finally:
        closer()

    write_bundle(export, out_dir)
    summary = export.summary()
    summary["out_dir"] = str(out_dir)
    summary["exporter_version"] = EXPORTER_VERSION
    json.dump(summary, sys.stdout, indent=1, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")
    print("catalog %s, patch %s, compatibility %s; %d gap(s)"
          % (export.catalog.catalog_hash[:12], export.profile.patch_id,
             export.profile.compatibility.value, len(export.gaps)),
          file=sys.stderr)
    for reason in export.report.reasons:
        print("  compatibility: %s" % reason, file=sys.stderr)
    if export.validation_errors:
        for problem in export.validation_errors:
            print("  invalid record: %s" % problem, file=sys.stderr)
        return EXIT_INTERNAL
    return EXIT_OK


# -------------------------------------------------------------- providers ---

def _replay_provider(args, request, captures):
    from .export import PobCatalogProvider
    from .reader import MappingCatalogReader
    from .sources import citations_from_payload

    try:
        raw = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Refused(EXIT_INVALID_REQUEST,
                       "row capture %s is not usable: %s" % (args.rows, exc)) from None
    reader = MappingCatalogReader(raw.get("tables") or {},
                                  raw.get("rule_sources") or {},
                                  source=str(args.rows))
    provider = PobCatalogProvider(
        reader,
        citations=citations_from_payload(raw.get("citations") or {}),
        release_captures=captures,
        pob_commit=raw.get("pob_commit"),
        pob_dirty_hash=raw.get("pob_dirty_hash"),
        adapter_version=raw.get("adapter_version") or "replayed",
        behaviour=None)
    return provider, lambda: None


def _engine_provider(args, request, captures):
    from ..evaluation import (EngineAdapter, BuildDocument, EngineState,
                              pob_worker_spec, resolve_checkout)
    from ..evaluation.errors import EngineError
    from .export import PobCatalogProvider
    from .reader import EngineCatalogReader
    from .sources import citations_to_payload, read_citations

    pob_root = args.pob_root or request.pob_root or os.environ.get("POB2_ROOT")
    if not pob_root or not Path(pob_root).is_dir():
        raise _Refused(
            EXIT_MISSING_DEPENDENCY,
            "no PoB checkout: pass --pob-root, set pob_root in the request, "
            "or set POB2_ROOT. Without the engine there is no catalog to "
            "export and no profile is written.")
    pob_root = str(Path(pob_root).resolve())
    checkout = resolve_checkout(pob_root)
    citations = read_citations(pob_root)

    try:
        spec = pob_worker_spec(pob_root)
    except EngineError as exc:
        raise _Refused(EXIT_MISSING_DEPENDENCY, str(exc)) from None
    adapter = EngineAdapter(spec, checkout=checkout,
                            screen_timeout_s=READ_TIMEOUT_S,
                            detailed_timeout_s=READ_TIMEOUT_S,
                            start_timeout_s=START_TIMEOUT_S)
    reader = EngineCatalogReader(adapter, timeout_s=READ_TIMEOUT_S)

    def behaviour(fixture):
        document = BuildDocument(build_hash="compat/%s" % fixture["fixture_id"],
                                 xml=fixture["document"])
        state = EngineState(stat_keys=tuple(sorted(fixture.get("expected") or {})))
        return adapter.probe(document, state, timeout_s=READ_TIMEOUT_S)

    provider = PobCatalogProvider(
        reader, citations=citations, release_captures=captures,
        pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
        behaviour=behaviour)

    def close():
        if args.capture_rows:
            _write_capture(args.capture_rows, reader, checkout, citations,
                           citations_to_payload)
        adapter.close()

    return provider, close


def _write_capture(path, reader, checkout, citations, to_payload) -> None:
    from ..evaluation import protocol

    payload: dict[str, Any] = {
        "capture_version": 1,
        "pob_commit": checkout.commit,
        "pob_dirty_hash": checkout.dirty_hash,
        "adapter_version": protocol.ADAPTER_VERSION,
        "citations": to_payload(citations),
        "rule_sources": reader.rule_sources(),
        "tables": {table: reader.rows(table)
                   for table in protocol.CATALOG_HANDLERS},
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False),
                   encoding="utf-8")
    print("row capture written to %s" % out, file=sys.stderr)
