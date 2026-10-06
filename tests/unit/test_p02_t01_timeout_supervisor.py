"""P02-T01 acceptance case 2: the request bound, proved by an outer supervisor.

A wedged worker never answers. Asserting the timeout from inside pytest would
mean that a broken bound hangs the suite rather than failing it, so the probe
runs as its own process under a hard outer deadline, and the deadline expiring
is the failure.

``scripts/p02_t01_timeout_probe.py`` does the work. This file is the
supervisor: it enforces the deadline, kills the whole process tree if the
deadline is reached, and reads the probe's JSON verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = "scripts/p02_t01_timeout_probe.py"

#: The adapter's bound for the probe's request.
REQUEST_BOUND_S = 2.0
#: The supervisor's bound. Generous enough for a cold spawn, far below any
#: value an unbounded wait would reach.
HARD_DEADLINE_S = 90.0


def run_probe(repo_root: Path, mode: str) -> dict:
    """Run one probe under a hard deadline; kill its tree if it overruns."""
    process = subprocess.Popen(
        [sys.executable, PROBE, "--mode", mode, "--timeout", str(REQUEST_BOUND_S)],
        cwd=str(repo_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    try:
        stdout, stderr = process.communicate(timeout=HARD_DEADLINE_S)
    except subprocess.TimeoutExpired:
        kill_tree(process.pid)
        process.communicate()
        pytest.fail(
            "the %s probe did not finish within %.0fs: the adapter did not "
            "enforce its %.1fs request bound" % (mode, HARD_DEADLINE_S,
                                                 REQUEST_BOUND_S))
    assert process.returncode == 0, (
        "probe %s exited %s\nstdout: %s\nstderr: %s"
        % (mode, process.returncode, stdout, stderr))
    return json.loads(stdout.strip().splitlines()[-1])


def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, check=False)
    else:  # pragma: no cover - the engine lane is Windows
        import os
        import signal
        os.kill(pid, signal.SIGKILL)


# -------------------------------------------------------------------- cases

def test_a_wedged_worker_produces_a_typed_bounded_timeout(repo_root: Path):
    report = run_probe(repo_root, "wedge")

    assert report["observed"] == "timeout"
    assert report["ok"] is True
    assert report["worker_alive_after"] is False
    assert report["parent_cwd_after"] == report["parent_cwd_before"]


def test_a_worker_that_leaves_produces_a_typed_crash(repo_root: Path):
    report = run_probe(repo_root, "crash")

    assert report["observed"] == "engine_crash"
    assert report["worker_alive_after"] is False
    assert "exit code 70" in report["diagnostic"]


def test_the_next_request_after_a_crash_runs_in_a_different_process(repo_root: Path):
    report = run_probe(repo_root, "revive")

    assert report["observed"] == "engine_crash"
    assert report["new_process"] is True
    assert report["first_worker_pid"] != report["second_worker_pid"]
    assert report["replacements"] == 1
    assert report["generation"] == 2
    # The replacement finished real work, and did it without clearing a build.
    assert report["revived_load"]["opt_setup_called"] is False
    assert report["revived_load"]["allocated_nodes"] > 0


@pytest.mark.parametrize("mode,stage", [
    ("combined", "primitives"), ("slow_load", "load_exact_build"),
    ("slow_primitives", "primitives"), ("slow_identity", "describe"),
    ("wedged_load", "load_exact_build"),
])
def test_evaluation_stages_share_one_deadline_and_recover(repo_root, mode, stage):
    report = run_probe(repo_root, mode)
    assert report["observed"] == "timeout"
    assert report["stage"] == stage
    assert not report["worker_alive_after"]
    assert report["new_process"] and report["reloaded"]
    # Windows taskkill and process joining each have a 10-second cleanup grace.
    assert report["elapsed_s"] < REQUEST_BOUND_S + 20


def test_multi_stage_evaluation_that_fits_the_budget_succeeds(repo_root):
    report = run_probe(repo_root, "within_budget")
    assert report["observed"] == "success"
    assert report["timeout_s"] == REQUEST_BOUND_S
    assert report["worker_alive_after"]
