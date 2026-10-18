"""Per-use engine values for one Flicker Strike cycle evaluation (P07-T01).

``CycleValues`` holds every number the timeline consumes, each with a trace
pointer to where it came from. It is built either from a frozen engine-output
bundle (``from_replay``, offline) or from the pinned engine through
``EngineAdapter`` (``capture``). Values are PoB-derived; nothing here is a
gameplay measurement.

Method ``pob-community-v2`` (D07 amendment 2026-10-18 (2)): Flicker Strike's
per-use values are PoB's own at the build's maximum Power Charges, with the
Charged Staff buff as PoB applies it. Charges are assumed, not generated.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

FLICKER = "Flicker Strike"
WHIRLING = "Whirling Assault"
CHARGED_STAFF = "Charged Staff"
POUNCE = "Pounce"

FLICKER_KEYS = ("AverageBurstHits", "AverageDamage", "AverageBurstDamage", "Speed",
                "TotalDPS", "ManaCost", "PowerCharges", "PowerChargesMax",
                "RemovablePowerCharges", "IgniteDPS")
SKILL_KEYS = ("Speed", "Time", "AverageDamage", "TotalDPS", "ManaCost",
              "AverageBurstHits", "AverageBurstDamage")
POOL_KEYS = ("Mana", "ManaRegenRecovery", "PowerChargesMax")

#: Flask fields the mana model reads.
FLASK_FIELDS = ("manaTotal", "instantPerc", "duration", "chargesUsed", "chargesMax",
                "gainBase")


class MissingValue(LookupError):
    """A required engine value is absent. The evaluator turns it into a gap."""

    def __init__(self, path: str, why: str):
        self.path = path
        self.why = why
        super().__init__("%s: %s" % (path, why))


@dataclass(frozen=True)
class FlaskValues:
    slot: str
    name: str
    mana_total: float
    instant_percent: float
    duration_s: float
    charges_used: float
    charges_max: float
    charges_per_s: float


@dataclass(frozen=True)
class CycleValues:
    """Everything the timeline reads, in seconds, mana and damage per strike."""

    document: str
    charges: int
    whirling_time_s: float
    whirling_mana: float
    #: Unscored. None when the source has no value for this document.
    whirling_damage_per_use: float | None
    charged_staff_time_s: float
    charged_staff_mana: float
    flicker_strikes_per_use: int
    flicker_strike_rate: float
    flicker_mana: float
    flicker_damage_per_strike_buffed: float
    flicker_damage_per_strike_unbuffed: float
    flicker_ignite_dps: float | None
    buff_duration_s: float
    mana_pool: float
    mana_regen_per_s: float
    flasks: tuple[FlaskValues, ...]
    pob_total_dps: float | None
    pob_burst_damage_per_use: float | None
    trace: Mapping[str, str] = field(default_factory=dict)
    #: Provenance recorded by the capture, never supplied by the evaluator:
    #: ``head`` (PoB commit), ``dirty_hash`` (None for a checked clean tree;
    #: the key is absent when unchecked), ``document_sha256`` (the scored
    #: document the values were read from) and ``state`` (what was applied).
    engine: Mapping[str, Any] = field(default_factory=dict)

    def mana_flask(self) -> FlaskValues | None:
        flasks = [f for f in self.flasks if f.mana_total > 0]
        return flasks[0] if flasks else None

    def to_json(self) -> dict:
        data = asdict(self)
        data["trace"] = dict(self.trace)
        data["engine"] = dict(self.engine)
        return data


def _need(row: Mapping[str, Any], key: str, path: str) -> float:
    value = row.get(key) if row is not None else None
    if value is None:
        raise MissingValue(path + "/" + key, "not in the engine output")
    return value


def _flask(slot: str, data: Mapping[str, Any], path: str) -> FlaskValues:
    fd = data.get("flaskData") or {}
    for key in FLASK_FIELDS:
        if fd.get(key) is None and not (key == "manaTotal"):
            raise MissingValue("%s/%s/flaskData/%s" % (path, slot, key), "not in the engine output")
    return FlaskValues(slot=slot, name=str(data.get("name", "")),
                       mana_total=float(fd.get("manaTotal") or 0.0),
                       instant_percent=float(fd["instantPerc"]),
                       duration_s=float(fd["duration"]),
                       charges_used=float(fd["chargesUsed"]),
                       charges_max=float(fd["chargesMax"]),
                       charges_per_s=float(fd["gainBase"]))


def buff_duration_s(duration: Mapping[str, Any], charges: int, path: str) -> float:
    """Charged Staff buff length: per-stack base x (1 + inc) x more x stacks.

    PoB carries ``ChargedStaffBuffDuration`` per stack but no module reads it
    (P09-T01.2 rule charged-staff-period), so the duration modifiers that
    apply to the skill are combined here, one stack per consumed charge.
    """
    base = duration.get("per_stack_ms_base")
    if not base:
        raise MissingValue(path + "/per_stack_ms_base", "Charged Staff buff base is absent")
    inc = duration.get("duration_inc", duration.get("inc"))
    more = duration.get("duration_more", duration.get("more"))
    if inc is None or more is None:
        raise MissingValue(path, "duration modifiers absent")
    return base / 1000.0 * (1 + inc / 100.0) * more * charges


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def from_replay(replay: Mapping[str, Any], *, source_xml: str, source_sha256: str,
                document: str = "benchmark", charges: int = 5,
                replay_ref: str = "replay.json") -> CycleValues:
    """Values from a frozen P09-T01.2 replay bundle.

    ``document``: ``benchmark`` (Pounce disabled, the scoring document) or
    ``seed`` (as imported, with Pounce's Predator's Mark).

    ``source_xml`` is the document the bundle names in ``build``; it must hash
    to ``source_sha256`` (recorded in the seed manifest). The bundle's engine
    identity and the scored document's hash are carried into the values.
    """
    if sha256_text(source_xml) != source_sha256:
        raise MissingValue("/build", "source document hashes to %s, the bundle's document "
                           "is %s" % (sha256_text(source_xml), source_sha256))
    if document == "seed":
        on, off = replay["flicker_seed"], replay["flicker_charged_staff_disabled"]
        on_ref, off_ref = "/flicker_seed", "/flicker_charged_staff_disabled"
    elif document == "benchmark":
        docs = replay["benchmark_documents"]
        on, off = docs["flicker_benchmark"], docs["flicker_benchmark_charged_staff_disabled"]
        on_ref = "/benchmark_documents/flicker_benchmark"
        off_ref = "/benchmark_documents/flicker_benchmark_charged_staff_disabled"
    else:
        raise ValueError("unknown document %r" % document)
    try:
        index = [r["forced_power_charges"] for r in on].index(charges)
        index_off = [r["forced_power_charges"] for r in off].index(charges)
    except ValueError:
        raise MissingValue("%s/forced_power_charges=%d" % (on_ref, charges),
                           "no row at that charge count") from None
    buffed, plain = on[index], off[index_off]
    diag = replay["diagnostics"]
    imported = diag["imported"]
    outputs = imported["outputs"]
    flasks = tuple(_flask(slot, data, "/diagnostics/imported/flasks")
                   for slot, data in sorted((imported.get("flasks") or {}).items()))
    wa, cs = replay["whirling_assault"], replay["charged_staff"]
    ref = replay_ref + "#"
    return CycleValues(
        document=document, charges=charges,
        whirling_time_s=_need(wa, "Time", "/whirling_assault"),
        whirling_mana=_need(wa, "ManaCost", "/whirling_assault"),
        # The bundle reads Whirling Assault and the imported outputs on the
        # seed document only. Their damage values carry Pounce's mark, so
        # they are left out of the benchmark document; times, costs and the
        # mana pool do not depend on Pounce (checked live, P07-T01 evidence).
        whirling_damage_per_use=(_need(wa, "AverageBurstDamage", "/whirling_assault")
                                 if document == "seed" else None),
        charged_staff_time_s=_need(cs, "Time", "/charged_staff"),
        charged_staff_mana=_need(cs, "ManaCost", "/charged_staff"),
        flicker_strikes_per_use=int(_need(buffed, "AverageBurstHits", on_ref)),
        flicker_strike_rate=_need(buffed, "Speed", on_ref),
        flicker_mana=_need(buffed, "ManaCost", on_ref),
        flicker_damage_per_strike_buffed=_need(buffed, "AverageDamage", on_ref),
        flicker_damage_per_strike_unbuffed=_need(plain, "AverageDamage", off_ref),
        flicker_ignite_dps=outputs.get("IgniteDPS") if document == "seed" else None,
        buff_duration_s=buff_duration_s(diag["charged_staff_duration"], charges,
                                        "/diagnostics/charged_staff_duration"),
        mana_pool=_need(outputs, "Mana", "/diagnostics/imported/outputs"),
        mana_regen_per_s=_need(outputs, "ManaRegenRecovery", "/diagnostics/imported/outputs"),
        flasks=flasks,
        pob_total_dps=buffed.get("TotalDPS"),
        pob_burst_damage_per_use=buffed.get("AverageBurstDamage"),
        trace={
            "whirling": ref + "/whirling_assault",
            "charged_staff": ref + "/charged_staff",
            "flicker_buffed": ref + "%s/%d" % (on_ref, index),
            "flicker_unbuffed": ref + "%s/%d" % (off_ref, index_off),
            "buff_duration": ref + "/diagnostics/charged_staff_duration",
            "mana": ref + "/diagnostics/imported/outputs",
            "flasks": ref + "/diagnostics/imported/flasks",
        },
        engine=_replay_identity(replay, source_xml, document, charges),
    )


def _replay_identity(replay, source_xml, document, charges) -> dict:
    engine = replay.get("engine") or {}
    adapter = engine.get("adapter_identity") or {}
    out = {"source": "frozen replay bundle", "build": replay.get("build"),
           "source_document_sha256": sha256_text(source_xml),
           "document_sha256": sha256_text(benchmark_document(source_xml)
                                          if document == "benchmark" else source_xml),
           "state": {"forced_power_charges": charges, "document": document}}
    if adapter.get("pob_commit") is not None:
        out["head"] = adapter["pob_commit"]
    if "pob_dirty_hash" in adapter:
        out["dirty_hash"] = adapter["pob_dirty_hash"]
    if adapter.get("adapter_version"):
        out["adapter_version"] = adapter["adapter_version"]
    return out


# ------------------------------------------------------------ live capture ===

def socket_groups(xml: str) -> list[tuple[int, str, bool]]:
    """(1-based index, first gem nameSpec, enabled) per socket group."""
    out = []
    for i, match in enumerate(re.finditer(r"<Skill [^>]*>", xml), start=1):
        head = match.group(0)
        name = re.search(r'nameSpec="([^"]+)"', xml[match.start():])
        out.append((i, name.group(1) if name else "", 'enabled="true"' in head))
    return out


def group_of(xml: str, gem: str) -> int:
    hits = [i for i, name, enabled in socket_groups(xml) if name == gem and enabled]
    if len(hits) != 1:
        raise MissingValue("/skills/" + gem, "expected one enabled socket group led by %r, "
                           "found %d" % (gem, len(hits)))
    return hits[0]


def disable_group(xml: str, index: int) -> str:
    """The document with socket group ``index`` (1-based) disabled."""
    starts = [m.start() for m in re.finditer(r"<Skill ", xml)]
    start = starts[index - 1]
    head = xml[start:xml.index(">", start)]
    if 'enabled="true"' not in head:
        raise LookupError("socket group %d is not enabled" % index)
    return xml[:start] + head.replace('enabled="true"', 'enabled="false"', 1) + xml[start + len(head):]


def benchmark_document(xml: str) -> str:
    """The scoring document: Pounce disabled (owner Q4: movement only; its
    Predator's Mark is a state the benchmark does not generate)."""
    try:
        return disable_group(xml, group_of(xml, POUNCE))
    except MissingValue:
        return xml


def capture(adapter, xml: str, *, document: str = "benchmark", charges: int = 5,
            build_hash: str = "p07-t01") -> CycleValues:
    """Values read live from the pinned engine through ``EngineAdapter``."""
    from ..evaluation import BuildDocument, EngineState

    doc = benchmark_document(xml) if document == "benchmark" else xml
    flicker, whirling, staff = (group_of(doc, FLICKER), group_of(doc, WHIRLING),
                                group_of(doc, CHARGED_STAFF))
    no_staff = disable_group(doc, staff)
    forced = {"usePowerCharges": True, "overridePowerCharges": charges}

    def read(name, text, state):
        return adapter.probe(BuildDocument(build_hash="%s/%s" % (build_hash, name), xml=text), state)

    buffed = read("flicker", doc, EngineState(config=forced, main_skill=(flicker, 1),
                                              stat_keys=FLICKER_KEYS))
    plain = read("flicker-no-staff", no_staff, EngineState(config=forced, main_skill=(flicker, 1),
                                                           stat_keys=FLICKER_KEYS))
    pool = read("pool", doc, EngineState(main_skill=(flicker, 1), stat_keys=POOL_KEYS + ("IgniteDPS",)))
    wa = read("whirling", doc, EngineState(main_skill=(whirling, 1), stat_keys=SKILL_KEYS))
    cs = read("charged-staff", doc, EngineState(main_skill=(staff, 1), stat_keys=SKILL_KEYS))
    extra = adapter.cycle_inputs(
        BuildDocument(build_hash="%s/cycle-inputs" % build_hash, xml=doc),
        EngineState(config={"usePowerCharges": True, "overridePowerCharges": 1},
                    main_skill=(staff, 1)))
    if extra.get("main_skill") != "ChargedStaffPlayer":
        raise MissingValue("/cycle_inputs/main_skill", "expected ChargedStaffPlayer, got %r"
                           % extra.get("main_skill"))
    flasks = tuple(_flask(slot, data, "/cycle_inputs/flasks")
                   for slot, data in sorted((extra.get("flasks") or {}).items()))
    identity = adapter.identity()
    engine = {"source": "EngineAdapter", "head": identity.pob_commit,
              "adapter_version": identity.adapter_version,
              "source_document_sha256": sha256_text(xml),
              "document_sha256": sha256_text(doc),
              "state": {"forced_power_charges": charges, "document": document},
              "worker_pids": list(getattr(adapter, "worker_pids", ()))}
    # A dirty hash of None means clean only when the checkout was resolved;
    # otherwise the tree state is unknown and the key stays absent.
    if getattr(adapter.checkout, "reason", "unresolved") is None:
        engine["dirty_hash"] = identity.pob_dirty_hash
    return CycleValues(
        document=document, charges=charges,
        whirling_time_s=_need(wa, "Time", "/whirling"),
        whirling_mana=_need(wa, "ManaCost", "/whirling"),
        whirling_damage_per_use=_need(wa, "AverageBurstDamage", "/whirling"),
        charged_staff_time_s=_need(cs, "Time", "/charged_staff"),
        charged_staff_mana=_need(cs, "ManaCost", "/charged_staff"),
        flicker_strikes_per_use=int(_need(buffed, "AverageBurstHits", "/flicker")),
        flicker_strike_rate=_need(buffed, "Speed", "/flicker"),
        flicker_mana=_need(buffed, "ManaCost", "/flicker"),
        flicker_damage_per_strike_buffed=_need(buffed, "AverageDamage", "/flicker"),
        flicker_damage_per_strike_unbuffed=_need(plain, "AverageDamage", "/flicker_no_staff"),
        flicker_ignite_dps=pool.get("IgniteDPS"),
        buff_duration_s=buff_duration_s(extra.get("duration") or {}, charges, "/cycle_inputs/duration"),
        mana_pool=_need(pool, "Mana", "/pool"),
        mana_regen_per_s=_need(pool, "ManaRegenRecovery", "/pool"),
        flasks=flasks,
        pob_total_dps=buffed.get("TotalDPS"),
        pob_burst_damage_per_use=buffed.get("AverageBurstDamage"),
        trace={
            "whirling": "engine: group %d main skill" % whirling,
            "charged_staff": "engine: group %d main skill" % staff,
            "flicker_buffed": "engine: group %d, %d forced charges" % (flicker, charges),
            "flicker_unbuffed": "engine: group %d, %d forced charges, group %d disabled"
                                % (flicker, charges, staff),
            "buff_duration": "engine: cycle_inputs, group %d" % staff,
            "mana": "engine: imported state outputs Mana, ManaRegenRecovery",
            "flasks": "engine: cycle_inputs flaskData",
        },
        engine=engine,
    )


SEED_REPLAY = "docs/evidence/P09-T01.2/replay.json"
SEED_MANIFEST = "docs/evidence/P09-T01.1/seed/manifest.json"


def seed_replay_values(repo_root, *, document: str = "benchmark") -> CycleValues:
    """The P09-T01.2 bundle's values, bound to the seed document it names.

    The document's expected SHA-256 comes from the P09-T01.1 seed manifest,
    so a changed or substituted seed file is refused.
    """
    import json
    from pathlib import Path

    root = Path(repo_root)
    replay = json.loads((root / SEED_REPLAY).read_text(encoding="utf-8"))
    manifest = json.loads((root / SEED_MANIFEST).read_text(encoding="utf-8"))
    build = replay["build"]
    expected = next(f["sha256"] for f in manifest["files"] if f["path"] == build)
    source = (root / build).read_bytes().decode("utf-8")
    return from_replay(replay, source_xml=source, source_sha256=expected, document=document,
                       replay_ref=SEED_REPLAY)
