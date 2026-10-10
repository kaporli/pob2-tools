"""``LegalityValidator.validate(build, profile)`` (P02-T03).

The boundary interfaces.md declares: it returns violations, unknowns and the
derived point and resource constraints. What it refuses to do is the point of
it.

It does not repair. A build that breaks a rule comes back illegal with the
rule named; nothing is dropped, clamped or reassigned to make it validate.

It does not guess. Every rule it applies comes from the ``PatchProfile``'s
``CharacterRules``. Where the profile has no rule, or where the caller
supplied no catalog, items or engine state, the answer is ``unknown`` and the
finding cites the gap that says what to collect.

It does not accept by default. A check that did not run is ``unknown``, never
``legal``, and the overall verdict is ``legal`` only when every declared check
answered ``legal``. On a profile exported from the current engine that cannot
happen for a build with equipment: ``SlotRule.accepted_base_categories`` is
empty with a blocking gap, so slot legality is undecidable and says so.
"""

from __future__ import annotations

from typing import Callable, Iterable, Mapping, Sequence

from ...domain.records import BuildSpec, GameCatalog, ItemInstance, PatchProfile
from . import checks as checkmod
from .context import build_context
from .gaps import GapFactory, utc_now
from .inputs import CatalogIndex, ImportedState, MeasuredState
from .report import DECLARED_CHECKS, LegalityReport, ReportBuilder

_ATTRIBUTE_AND_SPIRIT_ONLY = (
    "an attribute or Spirit result is two of the %d declared checks; passing "
    "them is not a legality verdict" % len(DECLARED_CHECKS))


class LegalityValidator:
    """Validate a build against the rules of one patch profile.

    The constructor takes what the validation may *read*; ``validate`` takes
    the build and the profile, as interfaces.md specifies. Every optional
    input changes which checks can be decided, never what the rules are.
    """

    def __init__(self, *,
                 catalog: GameCatalog | CatalogIndex | None = None,
                 items: Mapping[str, ItemInstance] | Iterable[ItemInstance] = (),
                 imported: ImportedState | None = None,
                 measured: MeasuredState | None = None,
                 clock: Callable[[], str] = utc_now) -> None:
        if isinstance(catalog, CatalogIndex):
            self.catalog = catalog
        else:
            self.catalog = CatalogIndex(catalog)
        self.items = _index_items(items)
        self.imported = imported
        self.measured = measured
        self.clock = clock

    def validate(self, build: BuildSpec, profile: PatchProfile) -> LegalityReport:
        self._check_inputs(build, profile)
        gaps = GapFactory(
            provenance_ids=[profile.record_id, build.record_id],
            subject_ids=[build.record_id, profile.record_id],
            clock=self.clock)
        ctx = build_context(build, profile, catalog=self.catalog,
                            items=self.items, imported=self.imported,
                            measured=self.measured, gaps=gaps)
        out = ReportBuilder()
        out.note(_ATTRIBUTE_AND_SPIRIT_ONLY)
        out.note("allocation read from the %s; equipment read from the %s"
                 % (ctx.allocation_source, ctx.equipment_source))
        if self.catalog.empty:
            out.note("no catalog was supplied, so nothing was resolved against "
                     "one")
        for check in checkmod.CHECKS:
            check(ctx, out)
        return out.build(build_hash=build.build_hash,
                         patch_profile_id=profile.record_id,
                         catalog_hash=profile.catalog_hash)

    # -- caller errors, not build problems ---------------------------------

    def _check_inputs(self, build: BuildSpec, profile: PatchProfile) -> None:
        if (self.catalog.catalog_hash is not None
                and self.catalog.catalog_hash != profile.catalog_hash):
            raise ValueError(
                "the supplied catalog is %s and the profile pins %s; "
                "validating a build against a catalog the profile does not "
                "pin would decide membership from the wrong data"
                % (self.catalog.catalog_hash, profile.catalog_hash))
        if build.catalog_hash and build.catalog_hash != profile.catalog_hash:
            raise ValueError(
                "build %s was resolved against catalog %s and the profile "
                "pins %s; re-resolve the build before validating it"
                % (build.build_hash, build.catalog_hash, profile.catalog_hash))
        imported = self.imported
        if (imported is not None and imported.build_hash is not None
                and imported.build_hash != build.build_hash):
            raise ValueError(
                "the imported engine state belongs to build %s and this is %s"
                % (imported.build_hash, build.build_hash))


def _index_items(
        items: Mapping[str, ItemInstance] | Iterable[ItemInstance]
        ) -> dict[str, ItemInstance]:
    if isinstance(items, Mapping):
        return dict(items)
    return {item.item_hash: item for item in items}
