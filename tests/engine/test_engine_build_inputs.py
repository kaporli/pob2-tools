"""Legitimate zero damage and malformed input, in the real engine (P00-T02/T04).

Two inputs the pipeline must keep apart:

* a valid build that simply has no skill - its full-DPS total is a real zero;
* a malformed build document - which must not look like a successful load.

The second case is observation P00-OBS-01, repaired by P02-T01.
``load_build_xml`` used to accept truncated, invalid XML and silently return a
default character, so "nothing was imported" was indistinguishable from "a
level 1 character was imported". It now raises, because PoB signals a document
it cannot read only by setting a UI prompt and carrying on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.engine


@pytest.fixture(scope="module")
def zero_dps_xml(fixtures_dir: Path) -> str:
    return (fixtures_dir / "builds" / "zero_dps_huntress.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def malformed_xml(fixtures_dir: Path) -> str:
    return (fixtures_dir / "builds" / "malformed_build.xml").read_text(encoding="utf-8")


# ------------------------------------------------------- legitimate zero

def test_a_skill_less_build_loads_and_reports_zero_full_dps(blank_build, zero_dps_xml: str):
    summary = blank_build.call("load_build_xml", {"xml": zero_dps_xml, "name": "zero"})

    assert summary["class"] == "Huntress"
    assert summary["level"] == 28
    assert blank_build.call("get_skills")["groups"] == []

    stats = blank_build.call("get_stats")
    assert stats["FullDPS"] == 0           # a real zero: nothing to include
    assert stats["Life"] > 0               # the build is calculated, not missing


def test_zero_full_dps_is_not_the_same_as_zero_hit_damage(blank_build, zero_dps_xml: str):
    """Characterized: PoB still reports a small unarmed hit for this build."""
    blank_build.call("load_build_xml", {"xml": zero_dps_xml, "name": "zero"})
    stats = blank_build.call("get_stats")

    assert stats["FullDPS"] == 0
    assert stats["TotalDPS"] > 0
    # Any future "is this build dealing damage?" rule must say which of the two
    # it means. That rule belongs to P02-T04, not to this characterization.


# ------------------------------------------------------- malformed input

def test_malformed_xml_is_rejected_instead_of_loading_a_default_character(
        blank_build, malformed_xml: str):
    """Repaired P00-OBS-01. It previously returned a level 1 character."""
    from pob2mcp.engine import PobEngineError

    with pytest.raises(PobEngineError) as excinfo:
        blank_build.call("load_build_xml", {"xml": malformed_xml, "name": "bad"})

    assert "invalid build document" in str(excinfo.value)
    # The reason the document was rejected is named, not just "failed".
    assert "unclosed element" in str(excinfo.value)


def test_the_declared_class_is_never_quietly_replaced_by_the_default_one(
        blank_build, malformed_xml: str):
    from pob2mcp.engine import PobEngineError

    assert "Huntress" in malformed_xml
    with pytest.raises(PobEngineError):
        blank_build.call("load_build_xml", {"xml": malformed_xml, "name": "bad"})

    # A real new build is still reachable, and is clearly a different request.
    fresh = blank_build.call("new_build")
    assert fresh["level"] == 1
    assert fresh["class"] != "Huntress"


# The typed ``invalid_input`` this produces at the adapter boundary is covered
# by tests/engine/test_p02_t01_engine_adapter.py.
