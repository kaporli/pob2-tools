"""`pob2opt parse --source ID --corpus DIR --catalog DIR` (P04-T01).

Reads a stored source document and its bytes from the corpus, parses them
against a catalog bundle written by ``pob2opt catalog export``, and stores
the ParseResult, BuildSpecs, items and claims in the same corpus. No network,
no PoB. JSON on stdout, prose on stderr.

The catalog bundle's records are imported into the corpus first, because a
BuildSpec names its catalog by hash and the corpus refuses a dangling one.

Exit codes: ``0`` parsed (the JSON ``status`` may still be ``partial``),
``2`` invalid request, ``3`` the format or catalog prevents parsing, ``4``
operational failure. Parsing the same source again under the same catalog and
options reports the stored result with the exit code it had; another catalog
or option is another parse (``pob.parse_key``), stored beside the first.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ..domain.codec import from_jsonable
from ..domain.enums import ParseResultStatus
from ..domain.records import (AcquisitionResult, DataGap, GameCatalog,
                              PatchProfile, SourceDocument)
from ..storage import RunStore
from ..storage.errors import DuplicateRecord
from . import formats
from .dispatch import parse_document
from .pob import ParseContext, record_base

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_BLOCKED = 3
EXIT_INTERNAL = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt parse",
        description="Create canonical records from stored source bytes.")
    parser.add_argument("--source", required=True,
                        help="SourceDocument record ID in the corpus")
    parser.add_argument("--corpus", required=True, help="corpus directory")
    parser.add_argument("--catalog", required=True,
                        help="catalog bundle directory from `catalog export`")
    parser.add_argument("--format", choices=list(formats.FORMATS),
                        default=None,
                        help="declare the format; the bytes must agree")
    parser.add_argument("--tree-version", default=None,
                        help="the catalog's passive tree version, for "
                             "naming documents saved on an older tree")
    return parser


def _load_catalog(directory: Path):
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))
    catalog = from_jsonable(GameCatalog, read("catalog.json"))
    profile = from_jsonable(PatchProfile, read("patch_profile.json"))
    gaps = [from_jsonable(DataGap, g) for g in read("gaps.json")]
    evidence = [from_jsonable(SourceDocument, json.loads(
        path.read_text(encoding="utf-8")))
        for path in sorted((directory / "evidence").glob("*.json"))]
    blobs = {path.name: path.read_bytes()
             for path in sorted((directory / "blobs").glob("*"))}
    acquisition = None
    if (directory / "acquisition.json").is_file():
        acquisition = from_jsonable(AcquisitionResult, read("acquisition.json"))
    return catalog, profile, gaps, evidence, blobs, acquisition


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[2:] if argv is None else argv))
    corpus = Path(args.corpus).resolve()
    bundle = Path(args.catalog).resolve()
    if not (bundle / "catalog.json").is_file():
        print("no catalog bundle at %s; run `pob2opt catalog export` first"
              % bundle, file=sys.stderr)
        return EXIT_BLOCKED
    try:
        catalog, profile, gaps, evidence, blobs, acquisition =             _load_catalog(bundle)
    except (OSError, ValueError, KeyError) as error:
        print("unreadable catalog bundle: %s" % error, file=sys.stderr)
        return EXIT_BLOCKED

    with RunStore.open_corpus(corpus) as store:
        try:
            document = store.get_source(args.source)
        except Exception as error:  # the store raises typed lookup errors
            print("no source document %r: %s" % (args.source, error),
                  file=sys.stderr)
            return EXIT_INVALID_REQUEST
        context = ParseContext(
            catalog_hash=catalog.catalog_hash,
            created_at=datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            entities=catalog.entities,
            current_tree_version=args.tree_version,
            declared_format=args.format)
        result_id = record_base(document, context)
        if store.has_record(result_id):
            stored = store.get_record(result_id)
            print(json.dumps(_report(stored, unchanged=True), indent=2,
                             sort_keys=True))
            print("already parsed: %s" % result_id, file=sys.stderr)
            return _exit_code(stored.status)

        # A catalog already in the corpus came with its bundle; its hash
        # names its content, so a later export of it adds nothing.
        if not store.has_record(catalog.record_id):
            try:
                for doc in evidence:
                    store.ingest_source(blobs[doc.blob_hash], doc)
                if acquisition is not None:
                    store.put_acquisition_result(acquisition)
                store.import_batch([*gaps, catalog, profile])
            except DuplicateRecord as error:
                print("the catalog bundle collides with records already in "
                      "the corpus (%s); re-export it with this version"
                      % error, file=sys.stderr)
                return EXIT_BLOCKED
        payload = store.read_payload(document.blob_hash)
        outcome = parse_document(document, payload, context)
        store.import_batch(outcome.records)

    report = _report(outcome.result, unchanged=False)
    report["builds"] = [{"record_id": b.record_id, "variant_id": b.variant_id,
                         "build_hash": b.build_hash,
                         "parse_status": b.parse_status.value}
                        for b in outcome.builds]
    report["items"] = len(outcome.items)
    report["claims"] = len(outcome.claims)
    print(json.dumps(report, indent=2, sort_keys=True))
    print("parse %s: %d build variant(s), %d issue(s)"
          % (outcome.result.status.value, len(outcome.builds),
             len(outcome.result.issues)), file=sys.stderr)
    return _exit_code(outcome.result.status)


def _exit_code(status: ParseResultStatus) -> int:
    if status in (ParseResultStatus.UNSUPPORTED_FORMAT,
                  ParseResultStatus.INVALID):
        return EXIT_BLOCKED
    return EXIT_OK


def _report(result, *, unchanged: bool) -> dict:
    return {
        "parse_result_id": result.record_id,
        "status": result.status.value,
        "parser_id": result.parser_id,
        "parser_version": result.parser_version,
        "source_document_id": result.source_document_id,
        "record_ids": list(result.record_ids),
        "issues": [{"code": i.code, "field_path": i.field_path,
                    "source_locator": i.source_locator,
                    "explanation": i.explanation} for i in result.issues],
        "field_coverage": [{"domain": c.domain, "present": c.present,
                            "resolved": c.resolved, "missing": c.missing}
                           for c in result.field_coverage],
        "unchanged": unchanged,
    }
