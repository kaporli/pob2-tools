"""Legitimate zero damage and malformed input, in the real engine (P00-T02/T04).

Two inputs the pipeline must keep apart:

* a valid build that simply has no skill - its full-DPS total is a real zero;
* a malformed build document - which must not look like a successful load.

The second case is an observation recorded by P00-T04 (P00-OBS-01): the current
``load_build_xml`` accepts truncated, invalid XML and silently returns a default
character, so "nothing was imported" is indistinguishable from "a level 1
character was imported".
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

def test_malformed_xml_is_accepted_and_yields_a_default_character(
        blank_build, malformed_xml: str):
    """CURRENT behaviour (observation P00-OBS-01): no error, no signal."""
    summary = blank_build.call("load_build_xml", {"xml": malformed_xml, "name": "bad"})

    assert summary["level"] == 1
    assert summary["passivePointsUsed"] == 0
    # The declared class in the document is Huntress; what loads is not.
    assert "Huntress" in malformed_xml
    assert summary["class"] != "Huntress"


def test_nothing_distinguishes_a_failed_import_from_a_real_level_one_build(
        blank_build, malformed_xml: str):
    bad = blank_build.call("load_build_xml", {"xml": malformed_xml, "name": "bad"})
    fresh = blank_build.call("new_build")

    assert bad["level"] == fresh["level"]
    assert bad["class"] == fresh["class"]
    assert bad["passivePointsUsed"] == fresh["passivePointsUsed"]


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="P00-OBS-01 repair belongs with P02-T01/P04-T01: malformed build input "
           "must produce a typed invalid_input result, not a default character.",
)
def test_repaired_malformed_import_is_rejected(blank_build, malformed_xml: str):
    from pob2mcp.engine import PobEngineError

    with pytest.raises(PobEngineError):
        blank_build.call("load_build_xml", {"xml": malformed_xml, "name": "bad"})
