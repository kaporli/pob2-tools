"""Only genuinely absent future services can count as expected failures."""
import importlib.util

import pytest

from repair_contracts import MissingFutureService, require_production_binding


def test_absent_service_has_a_specific_exception(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(MissingFutureService):
        require_production_binding("pob2opt.search", "P08-T01")


def test_present_service_requires_actual_production_tests(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    with pytest.raises(pytest.fail.Exception, match="now exists"):
        require_production_binding("pob2opt.search", "P08-T01")


def test_broken_import_is_not_missing_implementation(monkeypatch):
    def broken(name):
        raise ModuleNotFoundError("a dependency is broken", name="some_dependency")
    monkeypatch.setattr(importlib.util, "find_spec", broken)
    with pytest.raises(ModuleNotFoundError, match="dependency is broken"):
        require_production_binding("pob2opt.search", "P08-T01")
