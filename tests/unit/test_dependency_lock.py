"""Fail closed on incomplete or drifting runtime/test installations."""
import pytest

from lock_dependencies import compare_inventory, read_pins, target_version


def installed(**packages):
    return {"pob2-mcp": "0.1.0", "pob2-optimizer": "0.1.0", "pip": "26", **packages}


def test_exact_inventory_accepts_only_explicit_bootstrap_exceptions():
    assert compare_inventory({"pytest": "9"}, installed(pytest="9"), {"pytest": "9"}) == []


@pytest.mark.parametrize("name", ["exceptiongroup", "tomli"])
def test_automatically_filled_dependency_is_rejected(name):
    errors = compare_inventory({"pytest": "9"}, installed(pytest="9", **{name: "1"}), {"pytest": "9"})
    assert errors == [f"installed outside lock: {name}==1"]


def test_missing_or_wrong_locked_versions_are_rejected():
    errors = compare_inventory({"pytest": "9", "tomli": "2"}, installed(pytest="8"), {"pytest": "9"})
    assert len(errors) == 2
    assert any("tomli" in error and "MISSING" in error for error in errors)


def test_changed_direct_requirement_requires_new_lock():
    assert compare_inventory({"pytest": "9"}, installed(pytest="9"), {"pytest": "10"})


@pytest.mark.parametrize("content", ["pytest>=9", "pytest==9; python_version < '3.11'", "pytest==9\npytest==9", ""])
def test_unsupported_or_ambiguous_pin_input_fails(tmp_path, content):
    path = tmp_path / "lock.txt"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_pins(path)


def test_wrong_platform_cannot_generate_a_windows_lock(monkeypatch):
    import lock_dependencies
    monkeypatch.setattr(lock_dependencies.sys, "platform", "linux")
    with pytest.raises(ValueError, match="native Windows"):
        target_version()
