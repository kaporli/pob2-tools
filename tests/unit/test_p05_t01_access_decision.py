"""P05-T01: the recorded access disposition stays honest.

These tests read documents. They do not contact a provider, and the unit
conftest blocks outbound sockets for the whole directory anyway. They exist so
that D01 cannot drift into claiming a live market route, and so that the P05
evidence cannot start carrying a credential.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISION = REPO_ROOT / "docs" / "decisions" / "D01-trade-access.md"
EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "P05"

# Required by docs/decisions/README.md, quoting docs/specs/research.md.
REQUIRED_SECTIONS = (
    "## Question",
    "## Sources consulted",
    "## What was actually observed",
    "## Proposed choice",
    "## Contracts affected",
    "## Review",
)


@pytest.fixture(scope="module")
def decision_text() -> str:
    assert DECISION.is_file(), f"{DECISION} is missing"
    return DECISION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def decision_prose(decision_text: str) -> str:
    """One line, so an assertion is not defeated by where the paragraph wraps."""
    return " ".join(decision_text.split())


def test_decision_record_carries_every_required_section(decision_text: str) -> None:
    missing = [s for s in REQUIRED_SECTIONS if s not in decision_text]
    assert not missing, f"D01 is missing required sections: {missing}"
    assert "- Date proposed: 2026-10-10" in decision_text
    assert re.search(r"^- Reviewer: \S.*$", decision_text, re.M)


def test_decision_is_not_self_accepted(decision_text: str) -> None:
    """An engineer writes the proposal. Only a reviewer resolves it.

    This used to require the record to say `unresolved` forever, which made a
    real review impossible to record. What has to hold is weaker and more to
    the point: the verdict is one of the three the lifecycle allows, an
    accepted record names a reviewer, and that reviewer is not the engineer
    who proposed it.
    """
    proposer = _field(decision_text, "Proposed by")
    reviewer = _field(decision_text, "Reviewer")
    verdict = _field(decision_text, "Verdict")
    status = _field(decision_text, "Status")

    assert verdict in ("unresolved", "accepted", "rejected"), verdict
    assert status in ("proposed, awaiting review", "accepted", "rejected"), status
    if verdict == "unresolved":
        assert status == "proposed, awaiting review"
    else:
        assert reviewer != "unresolved"
        assert reviewer != proposer
        assert _field(decision_text, "Date resolved") != "unresolved"


def _field(text: str, name: str) -> str:
    match = re.search(r"^- %s: (.+)$" % re.escape(name), text, re.M)
    assert match, "D01 has no %s field" % name
    return match.group(1).strip()


def test_public_market_route_is_recorded_unsupported(decision_prose: str) -> None:
    assert "Route B, public market acquisition: `unsupported_access`" in decision_prose
    assert "R05 live-market acceptance stays blocked" in decision_prose


def test_account_route_is_conditional_not_satisfied(decision_prose: str) -> None:
    """Route A is approved in principle. The registration condition is open."""
    heading = (
        "Route A, account-character import: supported subject to a named "
        "registration condition"
    )
    assert heading in decision_prose
    assert "We do not have one" in decision_prose
    assert "conditions to check at implementation time, not satisfied conditions" in decision_prose


def test_no_borrowed_identity_or_cookie_is_blessed(decision_prose: str) -> None:
    assert "must not be implemented against a borrowed identity" in decision_prose
    assert "is the workaround P05-T01 forbids" in decision_prose
    assert "Not an alternative: a cookie, a borrowed `client_id`" in decision_prose


def test_refresh_failure_payload_is_specified(decision_text: str) -> None:
    """P05-T04 implements this; P05-T01 fixes what it must emit."""
    blocks = re.findall(r"```json\n(.*?)```", decision_text, flags=re.DOTALL)
    assert len(blocks) == 1, "expected exactly one JSON payload example in D01"
    payload = json.loads(blocks[0])

    assert payload["status"] == "unsupported_access"
    assert payload["operation"] == "market.refresh"
    assert payload["retry_eligible"] is False
    assert payload["http_status"] is None
    assert payload["availability"] == "unknown"
    assert payload["listings_rechecked"] == 0
    assert payload["decision_ref"] == "D01"

    prose = " ".join(decision_text.split())
    # interfaces.md: 3 is missing dependency/access/coverage.
    assert "exits `3`" in prose
    assert "Exit `0` is not permitted for this path" in prose
    # A refresh that could not run is never proof of a sale.
    assert "None moves to `unavailable`" in prose


def test_evidence_files_are_present_and_labelled() -> None:
    expected = {"access-observations.md", "transport-assumptions.md"}
    present = {p.name for p in EVIDENCE_DIR.glob("*.md")}
    assert expected <= present, f"missing P05 evidence: {sorted(expected - present)}"

    raw = (EVIDENCE_DIR / "access-observations.md").read_text(encoding="utf-8")
    observations = " ".join(raw.split())
    assert "Classification: `restricted`" in observations
    assert "Kind of evidence: documentary" in observations


# A cookie value, a bearer token or an OAuth code would look like one of these.
SECRET_SHAPES = (
    re.compile(r"POESESSID\s*[=:]\s*[\"']?[0-9a-fA-F]{16,}"),
    re.compile(r"(?i)\b(bearer|access_token|refresh_token)\b\s*[=:]\s*[\"']?[\w\-.]{20,}"),
    re.compile(r"(?i)\bcode_verifier\b\s*[=:]\s*[\"']?[\w\-.]{20,}"),
)


@pytest.mark.parametrize("path", sorted(EVIDENCE_DIR.rglob("*")), ids=lambda p: p.name)
def test_p05_evidence_stores_no_credential(path: Path) -> None:
    if not path.is_file():
        pytest.skip("directory")
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in SECRET_SHAPES:
        assert not pattern.search(text), f"{path.name} looks like it carries a credential"
