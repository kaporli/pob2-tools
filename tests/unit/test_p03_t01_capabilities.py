"""P03-T01: the three recorded capability manifests hold their shape.

These tests read committed evidence files. They never contact a provider and
they make no claim about what a provider does today; they check that the
manifests say what P03-T01 requires them to say, in the vocabulary the
contracts define, and that nothing in them is an undeclared claim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pob2opt.domain.enums import AccessMethod, AcquisitionStatus, Redistribution
from pob2opt.sources import CATEGORIES, SUPPORT_FLAGS, validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "P03"
DECISION = REPO_ROOT / "docs" / "decisions" / "D02-source-capabilities.md"

PROVIDERS = ("mobalytics", "maxroll", "poe-ninja")


def load(slug: str) -> dict:
    return json.loads((EVIDENCE / ("%s-capabilities.json" % slug)).read_text("utf-8"))


@pytest.fixture(params=PROVIDERS)
def manifest(request):
    return request.param, load(request.param)


def test_every_named_provider_has_a_manifest():
    present = sorted(p.name for p in EVIDENCE.glob("*-capabilities.json"))
    assert present == sorted("%s-capabilities.json" % s for s in PROVIDERS)


def test_each_manifest_satisfies_the_structure(manifest):
    slug, doc = manifest
    assert validate_manifest(doc, slug) == []


def test_each_manifest_is_either_reproducible_or_specifically_blocked(manifest):
    """The P03-T01 acceptance rule, checked literally."""
    _, doc = manifest
    example = doc.get("reproducible_acquisition_example")
    blocked = doc["blocked_cases"]
    assert example is not None or blocked, "neither an example nor a blocked case"
    for case in blocked:
        assert case["url"], "a blocked case without a URL is not specific"
        assert case["reason"] if "reason" in case else case["status"]
        assert case["status"] in set(AcquisitionStatus)
        assert case["evidence_id"]


def test_the_three_support_flags_are_separate_and_each_cites_evidence(manifest):
    _, doc = manifest
    support = doc["support"]
    assert sorted(support) == sorted(SUPPORT_FLAGS)
    for flag in SUPPORT_FLAGS:
        entry = support[flag]
        assert isinstance(entry["supported"], bool)
        assert isinstance(entry["confirmed"], bool)
        assert entry["note"], "%s has no note" % flag
        assert entry["evidence_ids"], "%s cites no evidence" % flag
        if entry["supported"]:
            assert entry["confirmed"], "%s is supported but unconfirmed" % flag
            assert entry["access_method"] in set(AccessMethod)


def test_all_five_representative_categories_are_answered(manifest):
    """A category that could not be inspected is recorded, not dropped."""
    _, doc = manifest
    records = doc["representative_records"]
    assert [r["category"] for r in records] == list(CATEGORIES)
    for record in records:
        assert isinstance(record["inspected"], bool)
        if not record["inspected"]:
            assert record["reason"], "%s gives no reason" % record["category"]
            assert record["status"] in set(AcquisitionStatus) | {"not_applicable"}


def test_redistribution_is_a_contract_value_and_handling_is_stated(manifest):
    _, doc = manifest
    assert doc["redistribution"] in set(Redistribution)
    assert doc["local_handling"] == "restricted"
    assert doc["redistribution_note"]


def test_no_manifest_claims_an_access_method_outside_the_contract(manifest):
    _, doc = manifest
    method = doc["access"]["permitted_access_method"]
    assert method is None or method in set(AccessMethod)
    assert doc["access"]["acquisition_status"] in set(AcquisitionStatus)
    for candidate in doc["access"]["candidate_access_methods"]:
        assert candidate in set(AccessMethod)
    for candidate in doc["recommended_adapter_path"]["access_methods"]:
        assert candidate in set(AccessMethod)


def test_the_inspection_declares_it_used_no_credentials(manifest):
    _, doc = manifest
    inspection = doc["inspection"]
    assert inspection["credentials_used"] is False
    assert inspection["cookies_used"] is False
    assert inspection["provider_contacted"] is False
    assert doc["bounds"]["crawl"] is False
    assert doc["bounds"]["undocumented_endpoints_probed"] is False


def test_no_manifest_carries_anything_that_looks_like_a_credential(manifest):
    """Evidence must never ship a cookie, token or key (docs/evidence/README)."""
    slug, _ = manifest
    text = (EVIDENCE / ("%s-capabilities.json" % slug)).read_text("utf-8")
    forbidden = re.compile(
        r"(set-cookie|authorization:|bearer\s+[A-Za-z0-9._-]{8,}"
        r"|api[_-]?key\s*[:=]|session(id)?\s*[:=]|POESESSID)", re.IGNORECASE)
    assert forbidden.search(text) is None


def test_each_manifest_records_the_robots_policy_it_read(manifest):
    _, doc = manifest
    robots = doc["robots"]
    assert robots["url"].endswith("/robots.txt")
    assert isinstance(robots["retrieved"], bool)
    assert robots["reading"], "a robots section with no reading is not evidence"
    if not robots["retrieved"]:
        assert robots["http_status"] is not None


def test_recorded_limits_are_never_looser_than_the_interface_defaults(manifest):
    _, doc = manifest
    applied = doc["limits"]["applied_defaults"]
    assert applied["connect_timeout_s"] <= 10
    assert applied["read_timeout_s"] <= 30
    assert applied["max_response_bytes"] <= 20 * 1024 * 1024
    assert applied["max_attempts"] <= 3


def test_browser_visible_text_is_never_counted_as_a_build_export(manifest):
    """Unconfirmed export routes stay unconfirmed."""
    _, doc = manifest
    for fmt in doc["structured_export_formats"]:
        assert isinstance(fmt["confirmed"], bool)
        if not fmt["confirmed"]:
            assert fmt["route"], "an unconfirmed format must say where it was reported"
    if not doc["support"]["full_build_data"]["confirmed"]:
        assert doc["support"]["full_build_data"]["supported"] is False


# ------------------------------------------------------- cross-provider ---

def test_no_provider_currently_supports_automatic_build_acquisition():
    """The finding this task returned. If it changes, this test must change."""
    for slug in PROVIDERS:
        doc = load(slug)
        assert doc["support"]["full_build_data"]["supported"] is False, slug
        assert doc["support"]["listing_metadata"]["supported"] is False, slug


def test_the_blocked_providers_are_blocked_for_a_named_reason():
    maxroll = load("maxroll")
    assert maxroll["access"]["acquisition_status"] == "unsupported_access"
    assert maxroll["redistribution"] == "restricted"
    assert maxroll["bounds"]["requests_to_provider_host"] == 1, (
        "only robots.txt may be requested from a host that disallows this agent")

    ninja = load("poe-ninja")
    assert ninja["access"]["acquisition_status"] == "unsupported_access"
    assert ninja["access"]["permitted_access_method"] == "documented_api"
    assert ninja["reproducible_acquisition_example"]["contains_build_data"] is False

    moba = load("mobalytics")
    assert moba["access"]["acquisition_status"] == "access_blocked"
    assert moba["access"]["permitted_access_method"] is None
    assert len(moba["blocked_cases"]) >= 5


def test_the_d02_proposal_carries_every_required_section():
    text = DECISION.read_text("utf-8")
    for heading in ("## The question", "## Sources consulted",
                    "## What was actually observed", "## Proposed choice",
                    "## Contracts affected", "## Reviewer", "## Date"):
        assert heading in text, heading
    assert "unresolved" in text.lower()
    assert "accepted" not in text.lower().split("## reviewer")[1]


def test_the_d02_proposal_does_not_resolve_itself():
    text = DECISION.read_text("utf-8")
    assert "Status: proposed, unresolved." in text
