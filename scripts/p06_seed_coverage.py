"""Coverage reports for the P09-T01.1 seed under registry p06-flicker-v1 (P06).

Offline. Reads the seed export, the committed engine parse evidence
(``docs/evidence/P06/seed-engine-mod-support.json``), the P09 scenarios and
the PoB charge table, and writes one report per scenario to
``docs/evidence/P06/``. No RotationPolicy exists for the seed (protocol.md:
none is written while Charged Staff's place is unresolved), so every report
runs without one and says so.

    python scripts/p06_seed_coverage.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pob2-optimizer"))

from pob2opt.coverage import analyse, decide  # noqa: E402
from pob2opt.coverage.flicker_v1 import build_registry  # noqa: E402
from pob2opt.coverage.inputs import (EngineState, build_facts_from_pob_xml,  # noqa: E402
                                     load_mod_support, load_scenarios)
from pob2opt.coverage.registry import PATCH_PROFILE_ID  # noqa: E402

SEED = REPO / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml"
PROBE = REPO / "docs/evidence/P06/seed-engine-mod-support.json"
SCENARIOS = REPO / "benchmarks/p09-flicker-v1/scenarios.json"
CHARGE_TABLE = REPO / "docs/evidence/P09-T01.1/pob-charge-table.json"
OUT = REPO / "docs/evidence/P06"
PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def seed_inputs() -> dict:
    table = json.loads(CHARGE_TABLE.read_text(encoding="utf-8"))
    facts = json.loads(SCENARIOS.read_text(encoding="utf-8"))["seed_facts"]
    rows = {str(r["power_charges"]): r for r in table["flicker_by_charges"]}

    def column(key):
        return {c: r[key] for c, r in sorted(rows.items())}

    def fact(name):
        value = facts[name]
        return value.get("value") if isinstance(value, dict) else value

    return {
        "/pob/FlickerStrikePlayer/AverageBurstDamage": column("AverageBurstDamage"),
        "/pob/FlickerStrikePlayer/AverageBurstHits": column("AverageBurstHits"),
        "/pob/FlickerStrikePlayer/Speed": column("Speed"),
        "/pob/FlickerStrikePlayer/ManaCost": rows["0"]["ManaCost"],
        "/pob/WhirlingAssaultPlayer/Time": table["whirling_assault"]["Time"],
        "/pob/WhirlingAssaultPlayer/ManaCost": table["whirling_assault"]["ManaCost"],
        "/pob/PowerChargesMax": fact("power_charges_max"),
    }


def build_reports() -> dict[str, dict]:
    registry = build_registry()
    # The charge table names the pinned HEAD but its working tree was not
    # checked, so the dirty flag is unknown, not False.
    facts = build_facts_from_pob_xml(SEED.read_bytes(), engine=EngineState(PIN, None))
    mods = load_mod_support(PROBE)
    inputs = seed_inputs()
    out = {}
    for sid, scenario in sorted(load_scenarios(SCENARIOS).items()):
        report = analyse(facts, scenario, registry, mod_support=mods,
                         patch_profile_id=PATCH_PROFILE_ID, patch_compatibility="partial",
                         pinned_commit=PIN, inputs=inputs)
        decision = decide(report, registry)
        counts: dict[str, int] = {}
        for f in report.findings:
            key = "%s/%s" % (f.severity.value, f.gap_class)
            counts[key] = counts.get(key, 0) + 1
        out[sid] = {
            "task": "P06-T02",
            "not_a_claim": ("Coverage of the seed under registry p06-flicker-v1. It states "
                            "which rules and inputs a score would need; it computes no score."),
            "generated_by": "scripts/p06_seed_coverage.py",
            "build": str(SEED.relative_to(REPO)).replace("\\", "/"),
            "rotation": None,
            "rotation_note": "No RotationPolicy exists for the seed; protocol.md writes none "
                             "while Charged Staff's place (Q10) is unresolved.",
            "registry": registry.summary(),
            "registry_hash": registry.registry_hash(),
            "inputs": inputs,
            "decision": {"eligible": decision.eligible,
                         "unsettled_critical": list(decision.unsettled_critical),
                         "blocking_gap_ids": list(decision.blocking_gap_ids),
                         "reasons": list(decision.reasons)},
            "counts": dict(sorted(counts.items())),
            "report": report.to_json(),
            "gaps": [_gap_json(g) for g in report.gaps()],
        }
    return out


def _gap_json(gap):
    from pob2opt.domain.codec import to_jsonable
    return to_jsonable(gap)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed files instead of writing")
    args = parser.parse_args()
    stale = []
    for sid, payload in build_reports().items():
        path = OUT / ("seed-coverage-%s.json" % sid)
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8")
        d = payload["decision"]
        print("%-24s eligible=%s blocking=%d %s" % (
            sid, d["eligible"], len(d["blocking_gap_ids"]), payload["counts"]))
    if stale:
        print("stale: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
