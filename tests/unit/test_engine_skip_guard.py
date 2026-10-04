"""The CI engine-skip guard rejects every way a run can go wrong (G0-R02).

The guard is the only thing standing between "engine tests skipped because no
runtime is configured" and "engine tests appear to have been fine". Its first
version read pytest's console summary and threw away the exit status, so a
fixture error passed it. These cases pin each failure mode.

The XML here is shaped like pytest's `--junitxml` output. The matching
end-to-end reproduction, running pytest with a deliberately broken fixture, is
recorded in docs/worklog/P00-T05.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from check_engine_skips import DEFAULT_REASON, GuardFailure, check

FULL_REASON = DEFAULT_REASON + ": set POB2_ROOT to a checkout whose runtime/lua51.dll exists"


def junit(tmp_path: Path, body: str, *, tests: int, errors: int = 0, failures: int = 0,
          skipped: int | None = None) -> Path:
    path = tmp_path / "engine-junit.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites><testsuite name="pytest" tests="%d" errors="%d" failures="%d" '
        'skipped="%d">%s</testsuite></testsuites>\n'
        % (tests, errors, failures, tests if skipped is None else skipped, body),
        encoding="utf-8")
    return path


def skipped_case(name: str, message: str = FULL_REASON) -> str:
    return ('<testcase classname="tests.engine.test_x" name="%s">'
            '<skipped type="pytest.skip" message="%s"></skipped></testcase>' % (name, message))


def passing_case(name: str) -> str:
    return '<testcase classname="tests.engine.test_x" name="%s"></testcase>' % name


# --------------------------------------------------------------- accepted

def test_a_clean_all_skipped_run_passes(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a") + skipped_case("b"), tests=2)
    notes = check(report, exit_code=0, reason=DEFAULT_REASON)
    assert "2 engine test(s) collected" in notes[0]


# --------------------------------------------------------------- rejected

def test_a_fixture_error_is_rejected(tmp_path: Path):
    """The exact case the previous guard accepted: 2 skipped, 1 error, exit 1."""
    report = junit(tmp_path, skipped_case("a") + skipped_case("b"), tests=3, errors=1, skipped=2)
    with pytest.raises(GuardFailure, match="exited 1"):
        check(report, exit_code=1, reason=DEFAULT_REASON)


def test_an_error_is_rejected_even_if_the_exit_code_lies(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a"), tests=2, errors=1, skipped=1)
    with pytest.raises(GuardFailure, match="error"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_a_failing_test_is_rejected(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a"), tests=2, failures=1, skipped=1)
    with pytest.raises(GuardFailure, match="failure"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_a_collection_error_is_rejected(tmp_path: Path):
    """pytest exits 2 and writes an errors count."""
    report = junit(tmp_path, "", tests=1, errors=1, skipped=0)
    with pytest.raises(GuardFailure, match="exited 2"):
        check(report, exit_code=2, reason=DEFAULT_REASON)


def test_an_empty_selection_is_rejected(tmp_path: Path):
    """Nothing collected is not evidence that engine tests skipped."""
    report = junit(tmp_path, "", tests=0)
    with pytest.raises(GuardFailure, match="no engine test was collected"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_pytest_exit_5_for_no_tests_is_rejected(tmp_path: Path):
    report = junit(tmp_path, "", tests=0)
    with pytest.raises(GuardFailure, match="exited 5"):
        check(report, exit_code=5, reason=DEFAULT_REASON)


def test_an_interrupted_run_is_rejected(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a"), tests=1)
    with pytest.raises(GuardFailure, match="exited 2"):
        check(report, exit_code=2, reason=DEFAULT_REASON)


def test_a_test_that_actually_ran_is_rejected(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a") + passing_case("b"), tests=2, skipped=1)
    with pytest.raises(GuardFailure, match="did not skip"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_an_xfail_is_not_accepted_as_a_runtime_skip(tmp_path: Path):
    """pytest records xfail as a skip; the reason is what distinguishes it."""
    xfailed = ('<testcase classname="tests.engine.test_x" name="b">'
               '<skipped type="pytest.xfail" message="F11 repair is P02-T01">'
               '</skipped></testcase>')
    report = junit(tmp_path, skipped_case("a") + xfailed, tests=2)
    with pytest.raises(GuardFailure, match="different reason"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_an_unrelated_skip_is_rejected(tmp_path: Path):
    report = junit(tmp_path, skipped_case("a", message="needs network"), tests=1)
    with pytest.raises(GuardFailure, match="different reason"):
        check(report, exit_code=0, reason=DEFAULT_REASON)


def test_a_missing_report_is_rejected(tmp_path: Path):
    with pytest.raises(GuardFailure, match="no JUnit report"):
        check(tmp_path / "absent.xml", exit_code=0, reason=DEFAULT_REASON)


def test_an_unparsable_report_is_rejected(tmp_path: Path):
    path = tmp_path / "engine-junit.xml"
    path.write_text("<testsuites><testsuite", encoding="utf-8")
    with pytest.raises(GuardFailure, match="not parsable"):
        check(path, exit_code=0, reason=DEFAULT_REASON)


def test_a_report_without_a_testsuite_is_rejected(tmp_path: Path):
    path = tmp_path / "engine-junit.xml"
    path.write_text("<testsuites></testsuites>", encoding="utf-8")
    with pytest.raises(GuardFailure, match="no testsuite"):
        check(path, exit_code=0, reason=DEFAULT_REASON)
