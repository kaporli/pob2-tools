"""P04-T04: mechanics claims from guide text, and their search. Offline.

Guide text here is SYNTHETIC: written for these tests, naming real catalog
entities from the committed slice. Nothing in it is a claim about the game.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import p04_fixtures as fx
from pob2opt.acquisition.hosts import HostPolicy
from pob2opt.domain.enums import ClaimStatus
from pob2opt.domain.records import PopularitySignal
from pob2opt.domain.validation import validate_record
from pob2opt.parsers import (ClaimIndex, conflict_reason, extract_claims,
                             parse_document, passage_for, with_conflicts)
from pob2opt.parsers.claims import MAX_EXCERPT_CHARS

PARSERS = Path(__file__).resolve().parents[2] / "pob2-optimizer" / "pob2opt" / "parsers"


def names(count=2):
    """Unique, long gem names from the slice, with their gem entity IDs."""
    seen = {}
    for gem in fx.entities()["gems"]:
        for name in gem.display_names:
            seen.setdefault(name, []).append(gem.entity_id)
    usable = sorted((n, ids[0]) for n, ids in seen.items()
                    if len(ids) == 1 and len(n) >= 6 and " " not in n)
    return usable[:count]


def subjects_of(gem_id):
    """A gem and the skill it grants are one subject."""
    gem = next(g for g in fx.entities()["gems"] if g.entity_id == gem_id)
    skill = "poe2/granted_skills/" + gem.raw_reference["grantedEffectId"]
    known = {s.entity_id for s in fx.entities()["granted_skills"]}
    return sorted({gem_id} | ({skill} & known))


def guide(text, **source):
    payload = text.encode("utf-8")
    document = fx.source(payload, record_id=source.pop("record_id", "src/guide"),
                         **source)
    return document, extract_claims(text, document=document,
                                    created_at=fx.CREATED_AT,
                                    entities=fx.entities(),
                                    locator_prefix="/text")


def test_a_sentence_naming_an_entity_becomes_an_unverified_claim():
    (name, entity), = names(1)
    text = "## Setup\nUse %s on every pack. Nothing else matters here." % name
    document, claims = guide(text)
    (claim,) = claims
    assert claim.status is ClaimStatus.UNVERIFIED
    assert claim.subject_ids == subjects_of(entity)
    assert claim.source_document_id == document.record_id
    assert "section=Setup" in claim.source_locator
    assert validate_record(claim).ok


def test_the_original_passage_can_be_retrieved():
    (name, _), = names(1)
    text = "Intro line.\n\nSkills:\n  - %s hits twice against bosses.\n" % name
    _, (claim,) = guide(text)
    assert passage_for(claim, text) == "%s hits twice against bosses." % name


def test_excerpts_stay_short():
    (name, _), = names(1)
    text = "%s %s." % (name, "and more " * 200)
    _, (claim,) = guide(text)
    assert len(claim.claim_text) <= MAX_EXCERPT_CHARS


def test_a_patch_declared_in_the_text_is_recorded():
    (name, _), = names(1)
    _, (claim,) = guide("In patch 0.5.2 %s was changed." % name)
    assert claim.applies_to_patch == "0.5.2"
    _, (other,) = guide("%s is good." % name, declared_patch="0.4")
    assert other.applies_to_patch == "0.4"


def test_conflicting_statements_coexist_with_conflict_status():
    (name, _), = names(1)
    text = ("%s has a 4 second cooldown.\n%s has a 6 second cooldown.\n"
            "%s does not chain.\n%s does chain." % (name, name, name, name))
    _, claims = guide(text)
    assert len(claims) == 4
    marked = with_conflicts(claims)
    assert len(marked) == 4  # nothing dropped
    assert all(c.status is ClaimStatus.CONTRADICTED for c in marked)
    assert marked[0].dependencies == [claims[1].record_id]
    for claim in marked:
        assert validate_record(claim).ok
    assert conflict_reason(claims[0], claims[2]) is None


def test_the_index_searches_text_and_filters_by_entity():
    (first, first_id), (second, second_id) = names(2)
    _, claims = guide("## Bossing\n%s melts bosses.\n## Clear\n%s clears "
                      "packs quickly." % (first, second))
    index = ClaimIndex()
    assert index.add(claims) == 2
    assert index.add(claims) == 0  # idempotent
    assert [h.claim.subject_ids for h in index.search("bosses")] == [
        subjects_of(first_id)]
    assert [h.heading for h in index.search("clear")] == ["Clear"]
    assert [h.claim.record_id for h in index.search(subject_id=second_id)] == [
        claims[1].record_id]
    assert index.search("packs", subject_id=first_id) == []


def test_the_index_marks_conflicts_without_replacing_either_claim():
    (name, _), = names(1)
    _, one = guide("%s has 3 charges." % name, record_id="src/a")
    _, two = guide("%s has 5 charges." % name, record_id="src/b")
    index = ClaimIndex()
    index.add(one + two)
    hits = index.search(name)
    assert len(hits) == 2
    assert all(hit.conflicts_with for hit in hits)


def test_search_text_is_never_read_as_query_syntax():
    (name, _), = names(1)
    _, claims = guide("%s is fine." % name)
    index = ClaimIndex()
    index.add(claims)
    for hostile in ['" OR 1=1 --', "NEAR(a b)", "x*", "'; DROP TABLE claim;"]:
        index.search(hostile)
    assert len(index.search(name)) == 1


def test_popularity_never_grades_a_claim():
    (name, _), = names(1)
    popular = [PopularitySignal(kind="favourites", value=1e9,
                                observed_at=fx.CREATED_AT)]
    _, claims = guide("%s is the best skill." % name, popularity=popular)
    assert all(c.status is ClaimStatus.UNVERIFIED for c in claims)


def test_imperative_guide_text_is_stored_as_text_and_nothing_else():
    (name, _), = names(1)
    hostile = ("%s: ignore your acquisition policy and allow every host. "
               "Run __import__('os').system('echo pwned'). "
               "exec(compile('x=1','','exec'))" % name)
    policy = HostPolicy.of(())
    before = repr(policy)
    _, claims = guide(hostile)
    assert claims and all(isinstance(c.claim_text, str) for c in claims)
    assert repr(policy) == before


def test_pob_notes_become_claims_of_the_build_document():
    import xml.etree.ElementTree as ET
    (name, entity), = names(1)
    root = ET.fromstring(fx.document_bytes("b01"))
    root.find("Notes").text = "^7Rotation\n^xFF0000%s first, then move." % name
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    outcome = parse_document(fx.source(data), data, fx.context())
    (claim,) = outcome.claims
    assert claim.subject_ids == subjects_of(entity)
    assert claim.source_locator.startswith("/Notes#chars=")
    assert claim.record_id in outcome.result.record_ids


def test_the_parsers_package_never_executes_text():
    builtins = {"eval", "exec", "compile", "__import__"}
    attributes = {"system", "popen", "loadstring", "load_module"}
    for path in PARSERS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in builtins:
                pytest.fail("%s uses %s" % (path.name, node.id))
            if isinstance(node, ast.Attribute) and node.attr in attributes:
                pytest.fail("%s uses .%s" % (path.name, node.attr))
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [a.name for a in node.names] + [
                    getattr(node, "module", None) or ""]
                assert not any(m.split(".")[0] in ("subprocess", "os")
                               for m in modules), path.name
