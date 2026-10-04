"""P00-only contract probes and synthetic data, not P01 record implementations.

P01 owns the actual schemas; P08 must bind the probes to its validated records
and dependency-injected local providers. The projection used by the probes is
an observation format for tests, not a prescribed production return type.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[1]
REQUIRED_REQUEST_KEYS = (
    "schema_version", "game", "class", "level", "patch_selection",
    "league_selection", "mode", "budget", "scenario_suite", "catalog_profile",
    "corpus_path", "item_pool_ids", "seed", "time_budget_s", "workers",
    "memory_limit_mb", "allow_weapon_switch", "allow_external_gear_swap",
    "execution_profile",
)


class MissingFutureService(Exception):
    """Only an absent service, never a validation/import/runtime failure."""


def require_production_binding(module, task):
    if importlib.util.find_spec(module) is None:
        raise MissingFutureService(f"{module} is not implemented ({task})")
    pytest.fail(
        f"{module} now exists: {task} must replace this placeholder with real "
        "contract tests using accepted P01 records and local provider/worker "
        "fixtures. Do not extend xfail to validation errors or missing imports.")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass
class PrepareObservation:
    cache_identity: str
    league_selection: str
    league_id: str
    budget_source: str
    catalog_hash: str
    passive_points: int
    ascendancy_points: int
    finalist_limit: int


def make_prepare_fixture(root):
    """Materialize all data read by SyntheticPrepare; no imaginary file paths.

    Snapshot shapes and point values are deliberately synthetic. They do not
    assert game rules or masquerade as accepted P01 schemas.
    """
    root.mkdir(exist_ok=True)
    catalog = {"kind": "synthetic", "budgets": {
        "28": {"passive_points": 31, "ascendancy_points": 0},
        "100": {"passive_points": 107, "ascendancy_points": 4}}}
    snapshots = {
        "catalog.json": catalog,
        "profile.json": {"kind": "synthetic", "patch_id": "fixture-patch-1", "catalog": "catalog.json"},
        "league.json": {"selection": "current_pc_challenge_trade", "resolved_id": "fixture-league-1"},
        "suite.json": {"kind": "synthetic", "scenario_ids": ["fixture-clear", "fixture-boss"]},
        "corpus.json": {"kind": "synthetic", "build_ids": ["fixture-build-1"]},
        "items.json": {"kind": "synthetic", "pool_id": "fixture-pool-1", "item_ids": ["fixture-item-1"]},
    }
    for name, value in snapshots.items():
        (root / name).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    request = json.loads((REPO / "docs/specs/examples/request.offline.json").read_text())
    request.update(scenario_suite=str(root / "suite.json"),
                   catalog_profile=str(root / "profile.json"), corpus_path=str(root / "corpus.json"),
                   item_pool_ids=["fixture-pool-1"], workers=1, finalist_limit=64)
    return request, SyntheticPrepare(root), digest(catalog)


class SyntheticPrepare:
    """A contract-test double only. Never substituted for the production service."""

    def __init__(self, root):
        self.root = root

    def __call__(self, request):
        jsonschema.validate(request, {"type": "object", "required": list(REQUIRED_REQUEST_KEYS)})
        snapshots = {name: json.loads((self.root / name).read_text()) for name in
                     ("catalog.json", "profile.json", "league.json", "suite.json", "corpus.json", "items.json")}
        for key, name in (("scenario_suite", "suite.json"), ("catalog_profile", "profile.json"), ("corpus_path", "corpus.json")):
            if Path(request[key]).resolve() != (self.root / name).resolve():
                raise ValueError(f"unresolved synthetic input: {key}")
        if request["item_pool_ids"] != [snapshots["items.json"]["pool_id"]]:
            raise ValueError("unresolved item pool")
        league = snapshots["league.json"]
        if request["league_selection"] != league["selection"]:
            raise ValueError("unresolved league selection")
        catalog = snapshots["catalog.json"]
        budget = catalog["budgets"][str(request["level"])]
        return PrepareObservation(
            digest({"request": request, "snapshots": snapshots}),
            request["league_selection"], league["resolved_id"], "catalog", digest(catalog),
            budget["passive_points"], budget["ascendancy_points"], request["finalist_limit"])


def assert_cache_identity(prepare, request, catalog_hash):
    low = prepare(dict(request, level=28))
    high = prepare(dict(request, level=100))
    assert low.cache_identity != high.cache_identity
    assert prepare(dict(request, level=28)).cache_identity == low.cache_identity


def assert_league_resolution(prepare, request, catalog_hash):
    result = prepare(deepcopy(request))
    assert result.league_selection == request["league_selection"]
    assert result.league_id == "fixture-league-1"


def assert_catalog_budget(prepare, request, catalog_hash):
    result = prepare(deepcopy(request))
    assert result.budget_source == "catalog"
    assert result.catalog_hash == catalog_hash
    assert (result.passive_points, result.ascendancy_points) == (107, 4)


def assert_candidate_limit(prepare, request, catalog_hash):
    for limit in (16, 64):
        assert prepare(dict(request, finalist_limit=limit)).finalist_limit == limit


PREPARE_PROBES = (assert_cache_identity, assert_league_resolution,
                  assert_catalog_budget, assert_candidate_limit)
