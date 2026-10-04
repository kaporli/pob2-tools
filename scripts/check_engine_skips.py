"""Verify that an engine test run skipped for the right reason (G0-R02).

The offline CI lane must prove something narrow: with no PoB runtime, every
selected engine test was collected and skipped because the runtime is missing.
The first version of that check read pytest's console summary and discarded its
exit status, so a fixture error (`34 skipped, 1 error`, exit 1) satisfied every
condition. This reads the JUnit report and the exit code instead.

    python -m pytest -m engine --junitxml=engine-junit.xml
    python scripts/check_engine_skips.py --exit-code $? --junit engine-junit.xml

Exit 0 means the run is a clean, complete, correctly reasoned skip. Any other
exit means the lane must fail, and the reason is printed.

A skipped engine test is not an engine pass. This script exists to keep that
true, not to turn a skip into evidence.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_REASON = "no usable PathOfBuilding-PoE2 runtime"


class GuardFailure(Exception):
    pass


def iter_suites(root: ET.Element):
    if root.tag == "testsuite":
        yield root
    for suite in root.iter("testsuite"):
        if suite is not root:
            yield suite


def check(junit_path: Path, exit_code: int, reason: str) -> list[str]:
    """Return the notes to print, or raise GuardFailure with the problem."""
    if exit_code != 0:
        raise GuardFailure(
            "pytest exited %d; a clean all-skipped run exits 0. An error, a "
            "failure, a collection error, an interrupt and an empty selection "
            "all land here." % exit_code)
    if not junit_path.is_file():
        raise GuardFailure("no JUnit report at %s" % junit_path)
    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError as exc:
        raise GuardFailure("JUnit report is not parsable: %s" % exc) from exc

    suites = list(iter_suites(root))
    if not suites:
        raise GuardFailure("JUnit report contains no testsuite element")

    total = errors = failures = 0
    for suite in suites:
        total += int(suite.get("tests", 0))
        errors += int(suite.get("errors", 0))
        failures += int(suite.get("failures", 0))
    if errors or failures:
        raise GuardFailure(
            "JUnit report records %d error(s) and %d failure(s); a skip-only run "
            "has neither." % (errors, failures))
    if total == 0:
        raise GuardFailure(
            "no engine test was collected. An empty selection is not evidence "
            "that engine tests skipped.")

    cases = [case for suite in suites for case in suite.iter("testcase")]
    if not cases:
        raise GuardFailure("JUnit report lists no testcase elements")

    not_skipped = []
    wrong_reason = []
    for case in cases:
        name = "%s::%s" % (case.get("classname", "?"), case.get("name", "?"))
        skipped = case.find("skipped")
        if skipped is None:
            not_skipped.append(name)
            continue
        text = " ".join(filter(None, [skipped.get("message", ""), skipped.text or ""]))
        if reason not in text:
            wrong_reason.append((name, text.strip()[:160]))

    if not_skipped:
        raise GuardFailure(
            "%d selected engine test(s) did not skip: %s"
            % (len(not_skipped), ", ".join(sorted(not_skipped)[:5])))
    if wrong_reason:
        detail = "; ".join("%s -> %s" % pair for pair in sorted(wrong_reason)[:5])
        raise GuardFailure(
            "%d engine test(s) skipped for a different reason than the missing "
            "runtime (an xfail or an unrelated skip is not proof): %s"
            % (len(wrong_reason), detail))

    return ["%d engine test(s) collected" % total,
            "all skipped with reason %r" % reason,
            "pytest exit code 0, no errors or failures"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path,
                        help="path to the JUnit XML report pytest wrote")
    parser.add_argument("--exit-code", required=True, type=int,
                        help="the exit code pytest returned")
    parser.add_argument("--reason", default=DEFAULT_REASON,
                        help="substring every skip message must contain")
    args = parser.parse_args(argv)
    try:
        notes = check(args.junit, args.exit_code, args.reason)
    except GuardFailure as failure:
        print("engine skip guard FAILED: %s" % failure, file=sys.stderr)
        return 1
    for note in notes:
        print("engine skip guard: %s" % note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
