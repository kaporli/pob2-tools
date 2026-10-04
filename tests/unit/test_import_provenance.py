"""The test run exercises this working tree, not an installed copy (P00-T02).

On the recorded development machine both packages were installed editable from
pre-monorepo standalone checkouts, so a plain ``import pob2opt`` resolved
outside this repository. Without this guard the whole suite could pass against
source nobody is editing.
"""

from __future__ import annotations

from pathlib import Path

import pob2mcp
import pob2opt


def test_pob2opt_is_imported_from_this_repository(repo_root: Path):
    origin = Path(pob2opt.__file__).resolve()
    assert origin.is_relative_to(repo_root), origin


def test_pob2mcp_is_imported_from_this_repository(repo_root: Path):
    origin = Path(pob2mcp.__file__).resolve()
    assert origin.is_relative_to(repo_root), origin


def test_the_doctor_check_agrees(repo_root: Path):
    from pob2opt import doctor

    check = doctor.check_package_provenance(repo_root)
    assert check.status == doctor.OK, check.summary
