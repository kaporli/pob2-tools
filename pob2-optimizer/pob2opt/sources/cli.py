"""`pob2opt source inspect --provider NAME --out DIR` (P03-T01).

A bounded capability report, never an automatic crawl. This command performs
no network access at all: it reads the manifest recorded for the provider in
``docs/evidence/P03``, checks its structure against the contract, and writes
the manifest and a short report into the output directory. If a provider's
access is unsupported or blocked, that is what the report says; there is no
flag that makes it try anyway.

JSON goes to stdout and prose to stderr, as interfaces.md requires. Exit codes
are the shared ones: 2 for an invalid request, 3 when no manifest exists for
the provider, 4 when the manifest on disk does not satisfy the structure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .manifests import (ManifestError, ManifestNotFound, known_providers,
                        load_manifest, resolve_provider, summarize)

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_MISSING_DEPENDENCY = 3
EXIT_INTERNAL = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt source inspect",
        description="Report one provider's recorded capability manifest. "
                    "Offline; it never contacts the provider.")
    parser.add_argument("--provider", required=True,
                        help="provider name; one of %s"
                             % ", ".join(known_providers()))
    parser.add_argument("--out", required=True,
                        help="directory for the manifest copy and the report")
    parser.add_argument("--manifest-dir", default=None,
                        help="read manifests from here instead of docs/evidence/P03")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[2:] if argv is None else argv))

    directory = Path(args.manifest_dir) if args.manifest_dir else None
    try:
        slug = resolve_provider(args.provider)
        manifest = load_manifest(slug, directory)
    except ManifestNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_MISSING_DEPENDENCY
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INTERNAL

    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
        report = summarize(manifest)
        _write(out / ("%s-capabilities.json" % slug), manifest)
        _write(out / ("%s-inspect-report.json" % slug), report)
    except OSError as exc:
        print("cannot write to %s: %s" % (out, exc), file=sys.stderr)
        return EXIT_INVALID_REQUEST

    print(_prose(report), file=sys.stderr)
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False, sort_keys=False)
    sys.stdout.write("\n")
    return EXIT_OK


def _write(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def _prose(report: dict) -> str:
    supported = [flag for flag, value in report["support"].items() if value]
    lines = [
        "%s: %s, inspected %s"
        % (report["provider"], report["acquisition_status"], report["inspected_at"]),
        "supported surfaces: %s" % (", ".join(supported) if supported else "none"),
        "representative categories inspected: %d of 5"
        % len(report["categories_inspected"]),
        "redistribution: %s, handled as %s"
        % (report["redistribution"], report["local_handling"]),
    ]
    return "\n".join(lines)
