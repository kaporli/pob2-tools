"""Evaluation identity and cache keys (P01-T04).

An evaluation may be reused only when **every** dependency in architecture.md
matches. They are listed once, here, as the fields of :class:`EvaluationKey`,
so adding a dependency is one edit and an immediate test failure anywhere it
was forgotten.

The nine dependencies the acceptance case names, and the field each one is:

======================  ==========================================
patch                   ``patch_profile_hash``
catalog                 ``catalog_hash``
engine                  ``pob_commit`` and ``pob_dirty_hash``
calibration             ``calibration_hash``
rotation                ``rotation_hash``
scenario                ``scenario_hash``
registry                ``mechanics_registry_hash``
fidelity                ``fidelity``
seed                    ``seed``
======================  ==========================================

plus ``build_hash``, ``adapter_version`` and ``evaluator_version``.

What is deliberately *not* here: timestamps, listing prices, source
popularity, display names. Those change the acquisition record, not the
combat result, so they must produce a cache hit.

Fidelity is both a key field and a separate rule. A stored ``screen`` result
can never answer a ``detailed`` request even though its key already differs,
so :func:`decide` probes for it and records
``CacheReason.FIDELITY_INSUFFICIENT`` instead of a bare "no entry". The reason
is persisted, because "why did this run recompute everything" is otherwise
unanswerable after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from .enums import CacheOutcome, CacheReason, Fidelity
from .identity import content_hash

#: The nine dependency names the P01-T04 acceptance case enumerates, mapped to
#: the key fields that carry them.
DEPENDENCY_FIELDS: dict[str, tuple[str, ...]] = {
    "patch": ("patch_profile_hash",),
    "catalog": ("catalog_hash",),
    "engine": ("pob_commit", "pob_dirty_hash"),
    "calibration": ("calibration_hash",),
    "rotation": ("rotation_hash",),
    "scenario": ("scenario_hash",),
    "registry": ("mechanics_registry_hash",),
    "fidelity": ("fidelity",),
    "seed": ("seed",),
}


@dataclass(frozen=True, slots=True)
class EvaluationKey:
    """Everything an evaluation's result depends on."""

    build_hash: str
    rotation_hash: str
    scenario_hash: str
    patch_profile_hash: str
    catalog_hash: str
    pob_commit: str
    pob_dirty_hash: str | None
    adapter_version: str
    mechanics_registry_hash: str
    calibration_hash: str
    evaluator_version: str
    fidelity: Fidelity
    seed: int

    def identity(self) -> dict[str, Any]:
        return {
            "build_hash": self.build_hash,
            "rotation_hash": self.rotation_hash,
            "scenario_hash": self.scenario_hash,
            "patch_profile_hash": self.patch_profile_hash,
            "catalog_hash": self.catalog_hash,
            "pob_commit": self.pob_commit,
            "pob_dirty_hash": self.pob_dirty_hash,
            "adapter_version": self.adapter_version,
            "mechanics_registry_hash": self.mechanics_registry_hash,
            "calibration_hash": self.calibration_hash,
            "evaluator_version": self.evaluator_version,
            "fidelity": self.fidelity.value,
            "seed": self.seed,
        }

    def cache_key(self) -> str:
        return content_hash(self.identity())

    def at_fidelity(self, fidelity: Fidelity) -> "EvaluationKey":
        return replace(self, fidelity=fidelity)

    @classmethod
    def from_manifest(
        cls,
        manifest: Any,
        *,
        build_hash: str,
        rotation_hash: str,
        scenario_hash: str,
        fidelity: Fidelity,
        seed: int | None = None,
    ) -> "EvaluationKey":
        """Take every shared dependency from the run's frozen manifest."""
        deps = manifest.dependency_hashes
        return cls(
            build_hash=build_hash,
            rotation_hash=rotation_hash,
            scenario_hash=scenario_hash,
            patch_profile_hash=deps.patch_profile_hash,
            catalog_hash=deps.catalog_hash,
            pob_commit=deps.pob_commit,
            pob_dirty_hash=deps.pob_dirty_hash,
            adapter_version=deps.adapter_version,
            mechanics_registry_hash=deps.mechanics_registry_hash,
            calibration_hash=deps.calibration_hash,
            evaluator_version=deps.evaluator_version,
            fidelity=fidelity,
            seed=manifest.rng_seed if seed is None else seed,
        )


@dataclass(frozen=True, slots=True)
class AggregateKey:
    """An aggregate score additionally depends on objective and baselines."""

    build_hash: str
    rotation_hash: str
    patch_profile_hash: str
    catalog_hash: str
    pob_commit: str
    pob_dirty_hash: str | None
    adapter_version: str
    mechanics_registry_hash: str
    calibration_hash: str
    evaluator_version: str
    objective_hash: str
    baseline_suite_hash: str

    def identity(self) -> dict[str, Any]:
        return {
            "build_hash": self.build_hash,
            "rotation_hash": self.rotation_hash,
            "patch_profile_hash": self.patch_profile_hash,
            "catalog_hash": self.catalog_hash,
            "pob_commit": self.pob_commit,
            "pob_dirty_hash": self.pob_dirty_hash,
            "adapter_version": self.adapter_version,
            "mechanics_registry_hash": self.mechanics_registry_hash,
            "calibration_hash": self.calibration_hash,
            "evaluator_version": self.evaluator_version,
            "objective_hash": self.objective_hash,
            "baseline_suite_hash": self.baseline_suite_hash,
        }

    def cache_key(self) -> str:
        return content_hash(self.identity())

    @classmethod
    def from_manifest(cls, manifest: Any, *, build_hash: str,
                      rotation_hash: str) -> "AggregateKey":
        deps = manifest.dependency_hashes
        return cls(
            build_hash=build_hash,
            rotation_hash=rotation_hash,
            patch_profile_hash=deps.patch_profile_hash,
            catalog_hash=deps.catalog_hash,
            pob_commit=deps.pob_commit,
            pob_dirty_hash=deps.pob_dirty_hash,
            adapter_version=deps.adapter_version,
            mechanics_registry_hash=deps.mechanics_registry_hash,
            calibration_hash=deps.calibration_hash,
            evaluator_version=deps.evaluator_version,
            objective_hash=deps.objective_hash,
            baseline_suite_hash=deps.baseline_suite_hash,
        )


@dataclass(frozen=True, slots=True)
class CacheDecision:
    """Why a lookup hit or missed. Persisted with the run."""

    cache_key: str
    outcome: CacheOutcome
    reason: CacheReason
    evaluation_id: str | None = None
    #: Set when a usable-looking entry was found but refused, e.g. a screen
    #: result that cannot answer a detailed request.
    rejected_cache_key: str | None = None
    detail: str | None = None

    @property
    def is_hit(self) -> bool:
        return self.outcome is CacheOutcome.HIT


def decide(
    key: EvaluationKey,
    lookup: Callable[[str], Any],
    *,
    legacy: Callable[[str], bool] | None = None,
) -> CacheDecision:
    """Resolve one cache lookup into a decision with its reason.

    ``lookup`` returns a stored evaluation for a cache key, or None.
    ``legacy`` reports whether a key belongs to an imported legacy phase
    result, which is readable but never cache-eligible.
    """
    cache_key = key.cache_key()
    found = lookup(cache_key)
    if found is not None:
        if legacy is not None and legacy(cache_key):
            return CacheDecision(
                cache_key, CacheOutcome.MISS, CacheReason.LEGACY_IMPORT,
                detail="a historical phase import is not a valid evaluation")
        return CacheDecision(cache_key, CacheOutcome.HIT, CacheReason.EXACT_MATCH,
                             evaluation_id=getattr(found, "evaluation_id", None))

    if key.fidelity is Fidelity.DETAILED:
        screen_key = key.at_fidelity(Fidelity.SCREEN).cache_key()
        if lookup(screen_key) is not None:
            return CacheDecision(
                cache_key, CacheOutcome.MISS, CacheReason.FIDELITY_INSUFFICIENT,
                rejected_cache_key=screen_key,
                detail="a screening result cannot satisfy a detailed request")

    return CacheDecision(cache_key, CacheOutcome.MISS, CacheReason.NO_ENTRY)
