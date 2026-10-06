"""Research finding F11 against the real engine (P00-T04).

``pob2opt.engine_worker.Worker.__init__`` used to run ``load_build_xml`` and
then ``OPT_setup``. This reproduces that exact pair of calls on a build that
has a passive tree, an equipped item and a socket group, and measures what
survives, because ``OPT_setup`` is still the right preparation for a blank
candidate and has to keep working.

P02-T01 repaired the import path by not calling ``OPT_setup`` at all, so the
repaired expectation at the bottom exercises the adapter rather than asking
``OPT_setup`` to behave differently.
"""

from __future__ import annotations

import pytest

from engine_helpers import FIXTURE_WEAPON, allocated_count, equipped_count, socket_group_count

pytestmark = pytest.mark.engine

CHAR_LEVEL = 28
RESIST_PENALTY = 0


@pytest.fixture()
def populated_build_xml(blank_build):
    """A build with tree, gear and a skill group - the things an import carries."""
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    blank_build.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    return blank_build.call("save_build_xml")["xml"]


def test_the_fixture_build_really_has_something_to_lose(blank_build, populated_build_xml):
    blank_build.call("load_build_xml", {"xml": populated_build_xml, "name": "import"})
    assert allocated_count(blank_build) > 1
    assert equipped_count(blank_build) == 1


def test_worker_init_sequence_erases_the_imported_character(
        blank_build, populated_build_xml, opt_helpers_source):
    blank_build.call("load_build_xml", {"xml": populated_build_xml, "name": "import"})
    nodes_after_import = allocated_count(blank_build)
    items_after_import = equipped_count(blank_build)

    # Exactly what Worker.__init__ does next.
    blank_build.eval_lua(opt_helpers_source)
    blank_build.eval_lua("return OPT_setup(%d, %d)" % (CHAR_LEVEL, RESIST_PENALTY))

    assert allocated_count(blank_build) < nodes_after_import
    assert allocated_count(blank_build) <= 1, "only the class root survives"
    assert equipped_count(blank_build) == 0 < items_after_import
    assert socket_group_count(blank_build) == 0


def test_the_wipe_is_silent(blank_build, populated_build_xml, opt_helpers_source):
    """`OPT_setup` returns a bare success; nothing reports what was discarded."""
    blank_build.call("load_build_xml", {"xml": populated_build_xml, "name": "import"})
    blank_build.eval_lua(opt_helpers_source)
    result = blank_build.eval_lua("return OPT_setup(%d, %d)" % (CHAR_LEVEL, RESIST_PENALTY))
    assert result is True


def test_setup_silently_loses_the_requested_character_level_in_auto_mode(
        blank_build, populated_build_xml, opt_helpers_source):
    """Observation P00-OBS-02.

    ``OPT_setup`` assigns ``build.characterLevel`` and then resets the passive
    tree. When the loaded build has ``characterLevelAutoMode`` enabled - which
    is what PoB writes for a newly created build - the level is recomputed from
    the now-empty tree and collapses to 1, while ``enemyLevel`` keeps the
    requested value. Every candidate would then be evaluated as a level 1
    character against a level 28 enemy, with nothing reporting the mismatch.
    """
    assert 'characterLevelAutoMode="true"' in populated_build_xml
    blank_build.call("load_build_xml", {"xml": populated_build_xml, "name": "import"})
    assert blank_build.call("get_build_info")["level"] > 1

    blank_build.eval_lua(opt_helpers_source)
    blank_build.eval_lua("return OPT_setup(%d, %d)" % (CHAR_LEVEL, RESIST_PENALTY))

    assert blank_build.call("get_build_info")["level"] == 1
    assert blank_build.call("get_config")["enemyLevel"] == CHAR_LEVEL


def test_the_requested_level_is_honoured_when_auto_mode_is_off(
        blank_build, opt_helpers_source):
    """The same call behaves correctly on a build with the flag cleared."""
    blank_build.eval_lua("build.characterLevelAutoMode = false; return true")
    blank_build.eval_lua(opt_helpers_source)
    blank_build.eval_lua("return OPT_setup(%d, %d)" % (CHAR_LEVEL, RESIST_PENALTY))

    assert blank_build.call("get_build_info")["level"] == CHAR_LEVEL


# ------------------------------------------------------- repaired behaviour
# Migrated by P02-T01. The original expectation called ``OPT_setup`` and asked
# the character to survive it, which would have required changing what
# ``OPT_setup`` means. The repair was to stop calling it on the import path, so
# the expectation now exercises that path instead.


def test_loading_without_opt_setup_keeps_the_whole_character(
        blank_build, populated_build_xml, opt_helpers_source):
    """The import path, minus the one call that was doing the damage.

    Loading the helper Lua is what the worker still does; only ``OPT_setup``
    is gone. The adapter equivalent, in its own worker process, is
    tests/engine/test_p02_t01_engine_adapter.py.
    """
    blank_build.call("load_build_xml", {"xml": populated_build_xml, "name": "import"})
    nodes = allocated_count(blank_build)
    items = equipped_count(blank_build)
    assert nodes > 1 and items == 1

    blank_build.eval_lua(opt_helpers_source)

    assert allocated_count(blank_build) == nodes
    assert equipped_count(blank_build) == items
