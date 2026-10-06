"""Load the record example fixtures (P01-T01).

``tests/fixtures/records/*.v1.json`` holds, per record kind, one valid example
plus the invalid and alternative-valid cases expressed as JSON Pointer patches
of it. Keeping the cases as patches means a reviewer reads the difference that
matters instead of diffing two full records.

Three marker values exist because JSON cannot express them:

``"__remove__"``  delete the key at that pointer
``"__nan__"``     insert ``float('nan')``
``"__inf__"``     insert ``float('inf')``
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "records"

REMOVE = "__remove__"
MARKERS = {"__nan__": float("nan"), "__inf__": float("inf")}


def _materialize(value: Any) -> Any:
    if isinstance(value, str) and value in MARKERS:
        return MARKERS[value]
    if isinstance(value, dict):
        return {k: _materialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_materialize(v) for v in value]
    return value


def _step(container: Any, token: str) -> tuple[Any, Any]:
    """Return (container, key) for one pointer token.

    ``-`` is the JSON Pointer end-of-array token, used here to append an
    element: a fixture that adds a second modifier writes ``/modifiers/-``.
    """
    if isinstance(container, list):
        if token == "-":
            container.append(None)
            return container, len(container) - 1
        return container, int(token)
    return container, token


def apply_patch(record: dict, patch: dict[str, Any]) -> dict:
    """Return a copy of ``record`` with every pointer in ``patch`` applied."""
    out = deepcopy(record)
    for pointer, value in patch.items():
        if not pointer.startswith("/"):
            raise ValueError("patch key %r is not a JSON Pointer" % pointer)
        tokens = pointer[1:].split("/")
        node = out
        for token in tokens[:-1]:
            node, key = _step(node, token)
            node = node[key]
        node, key = _step(node, tokens[-1])
        if value == REMOVE:
            del node[key]
        else:
            node[key] = _materialize(value)
    return out


def load_files() -> dict[str, dict]:
    files = sorted(FIXTURE_DIR.glob("*.v1.json"))
    if not files:  # pragma: no cover - packaging error
        raise FileNotFoundError("no record fixtures in %s" % FIXTURE_DIR)
    return {path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in files}


def load_cases() -> dict[str, dict]:
    """``record kind -> {file, valid, also_valid, invalid}``."""
    cases: dict[str, dict] = {}
    for name, doc in load_files().items():
        for kind, entry in doc["records"].items():
            if kind in cases:
                raise AssertionError("%s is defined in two fixture files" % kind)
            cases[kind] = dict(entry, file=name)
    return cases


def valid_payloads() -> dict[str, dict]:
    return {kind: entry["valid"] for kind, entry in load_cases().items()}


def records() -> dict[str, Any]:
    """The valid example of every kind, decoded into its dataclass."""
    from pob2opt.domain import RECORD_TYPES, from_jsonable

    return {kind: from_jsonable(RECORD_TYPES[kind], payload)
            for kind, payload in valid_payloads().items()}


def extra_records() -> list[Any]:
    """Valid records that exist only so the reference graph closes.

    The capture behind the independent observation, and the acquisition that
    produced it. They are indexed and validated like any other record but are
    not the one documented example of their kind.
    """
    from pob2opt.domain import RECORD_TYPES, from_jsonable

    out = []
    for doc in load_files().values():
        for entry in doc.get("extra_records", []):
            out.append(from_jsonable(RECORD_TYPES[entry["kind"]],
                                     entry["record"]))
    return out


def all_records() -> list[Any]:
    """Every valid fixture record: the documented examples plus the extras."""
    return list(records().values()) + extra_records()


def closed_index():
    """A corpus in which every fixture reference resolves."""
    from pob2opt.domain import RecordIndex

    return RecordIndex.from_records(all_records(), blob_payloads())


#: Kinds that reference each other and therefore import as one batch.
#: patch_profile cites the catalog that cites it, and also cites a gap in
#: another table, so no insertion order would satisfy all three.
CORE_BATCH = (
    "patch_profile", "game_catalog", "item_instance", "listing", "build_spec",
    "scenario_spec", "rotation_policy", "mechanic_claim", "mechanic_rule",
    "parse_result", "data_gap", "run_manifest", "observation",
)


def seed_corpus(store, *, with_results: bool = True) -> dict[str, Any]:
    """Load the whole closed fixture graph into a store, in dependency order.

    Every reference resolves afterwards, so the store is a corpus a run can
    actually be built from. Returns the records by kind.
    """
    R = records()
    payloads = blob_payloads()

    for record in [R["source_document"]] + [
            r for r in extra_records() if type(r).__name__ == "SourceDocument"]:
        store.ingest_source(payloads[record.blob_hash], record)
    for record in [R["acquisition_result"]] + [
            r for r in extra_records()
            if type(r).__name__ == "AcquisitionResult"]:
        store.put_acquisition_result(record)

    store.import_batch([R[kind] for kind in CORE_BATCH])
    if with_results:
        store.commit_evaluation(None, R["evaluation_result"])
        store.put_normalized(R["aggregate_result"])
    return R





def blob_payloads() -> dict[str, bytes]:
    """The original bytes the fixture source documents were acquired from."""
    out: dict[str, bytes] = {}
    for doc in load_files().values():
        for blob_hash, text in doc.get("blob_payloads", {}).items():
            out[blob_hash] = text.encode("utf-8")
    return out
