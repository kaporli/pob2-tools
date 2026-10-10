"""Reading the engine's own state after an import (P02-T03).

`read_imported_state` loads a build's document exactly, through P02-T01's
adapter and nobody else's, and reads back what the engine holds. There is no
second engine path here: the bounds, the worker replacement and the typed
failures are the adapter's.

Why this exists at all: PoB imports documents it will not police. A build
whose tree is disconnected, whose level is below what its gear requires or
whose allocation exceeds any budget loads without a prompt and calculates
happily. A clean import is therefore evidence that the document parsed, and
of nothing else.
"""

from __future__ import annotations

from ...domain.records import BuildSpec, PatchProfile
from ..protocol import BuildDocument
from .inputs import ImportedState


def read_imported_state(adapter, build: BuildSpec, profile: PatchProfile, *,
                        document: BuildDocument | None = None,
                        blob_hash: str | None = None,
                        timeout_s: float | None = None) -> ImportedState:
    """Load ``build`` exactly and return the engine's own view of it.

    The document is the build's own stored one unless the caller supplies it.
    Nothing here configures the build, sets a main skill or recalculates: the
    engine's state is read as the load left it.
    """
    payload, used_document = adapter.legality_state(
        build, profile, document=document, blob_hash=blob_hash,
        timeout_s=timeout_s)
    return ImportedState.from_wire(payload,
                                   document_hash=used_document.content_hash,
                                   build_hash=build.build_hash)
