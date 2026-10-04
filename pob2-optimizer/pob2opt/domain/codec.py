"""Dataclass to JSON conversion driven by the declared type hints (P01-T01).

One generic codec instead of two hand-written methods per record. Hand-written
serializers drift from their dataclass silently; this one cannot, because the
annotation is the only thing it reads.

What it encodes:

* dataclasses                 -> object, absent fields omitted
* ``Enum``                    -> its ``value``
* ``None``                    -> ``null`` (unknown, per ``absent.py``)
* ``ABSENT``                  -> key omitted
* ``list[T]`` / ``dict[str, T]`` -> array / object, recursively
* ``str``/``int``/``float``/``bool`` -> themselves
* ``Any``                     -> passed through after a JSON-safety check

Decoding is the same walk in reverse: the annotation says what to build, so a
``"detailed"`` string becomes ``Fidelity.DETAILED`` and a nested object becomes
its dataclass. An unexpected key is an error rather than a silently dropped
field, because losing an imported modifier is the failure contracts.md spends
most of its length preventing.

Floats are checked here as well as in validation: ``float('nan')`` survives
``json.dumps`` under the default settings and would poison every hash.
"""

from __future__ import annotations

import dataclasses
import math
import types
import typing
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints

from .absent import ABSENT, Absent

_HINT_CACHE: dict[type, dict[str, Any]] = {}


def json_key(field: dataclasses.Field) -> str:
    """The JSON name of a field.

    Only needed where the specification's key is a Python keyword: the
    RunRequest key is ``class``, so the attribute is ``class_id`` carrying
    ``metadata={"json_key": "class"}``.
    """
    return str(field.metadata.get("json_key", field.name))


class CodecError(TypeError):
    """A record could not be converted. Always names the field path."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__("%s: %s" % (path or "/", message))
        self.path = path or "/"
        self.message = message


def hints_for(cls: type) -> dict[str, Any]:
    """Resolved annotations for a dataclass, cached.

    ``from __future__ import annotations`` makes every annotation a string, so
    they have to be evaluated against the defining module once.
    """
    cached = _HINT_CACHE.get(cls)
    if cached is None:
        cached = get_type_hints(cls, include_extras=False)
        _HINT_CACHE[cls] = cached
    return cached


def _is_optional_like(ann: Any) -> tuple[bool, bool, list[Any]]:
    """Split a union into (allows None, allows ABSENT, remaining members)."""
    origin = get_origin(ann)
    if origin is not Union and origin is not types.UnionType:
        return False, False, [ann]
    allows_none = False
    allows_absent = False
    rest: list[Any] = []
    for member in get_args(ann):
        if member is type(None):
            allows_none = True
        elif member is Absent:
            allows_absent = True
        else:
            rest.append(member)
    return allows_none, allows_absent, rest


class NotANumber(CodecError):
    """NaN or Infinity reached a record. Reported separately so validation
    can name it rather than call it a generic shape problem."""


def _check_number(value: float, path: str) -> float:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise NotANumber(
            path, "%s is not a value; JSON has no NaN or Infinity"
            % ("NaN" if math.isnan(value) else "Infinity"))
    return value


# ------------------------------------------------------------------ encoding

def to_jsonable(value: Any, *, path: str = "") -> Any:
    """Convert a record (or any supported value) to JSON-ready Python."""
    if value is ABSENT:
        raise CodecError(path, "ABSENT must be dropped by its container")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (int, float)):
        return _check_number(value, path)
    if isinstance(value, str):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: dict[str, Any] = {}
        for field in dataclasses.fields(value):
            item = getattr(value, field.name)
            if item is ABSENT:
                continue
            key = json_key(field)
            out[key] = to_jsonable(item, path="%s/%s" % (path, key))
        return out
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v, path="%s/%d" % (path, i)) for i, v in enumerate(value)]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CodecError(path, "object keys must be strings, got %r" % (key,))
            if item is ABSENT:
                continue
            out[key] = to_jsonable(item, path="%s/%s" % (path, key))
        return out
    raise CodecError(path, "%s is not persistable" % type(value).__name__)


# ------------------------------------------------------------------ decoding

def from_jsonable(ann: Any, value: Any, *, path: str = "") -> Any:
    """Build the value the annotation describes out of plain JSON data."""
    allows_none, _allows_absent, members = _is_optional_like(ann)
    if value is None:
        if allows_none:
            return None
        raise CodecError(path, "null is not allowed here")

    if len(members) != 1:
        # Only the small unions the records actually use are supported; a wider
        # one would need discriminator rules this layer must not invent.
        for member in members:
            try:
                return from_jsonable(member, value, path=path)
            except CodecError:
                continue
        raise CodecError(path, "value matches no member of %r" % (ann,))

    target = members[0]
    origin = get_origin(target)

    if target is Any:
        return _check_jsonable_any(value, path)
    if isinstance(target, type) and issubclass(target, Enum):
        try:
            return target(value)
        except ValueError:
            allowed = ", ".join(sorted(str(m.value) for m in target))
            raise CodecError(path, "unknown %s %r; allowed: %s"
                             % (target.__name__, value, allowed)) from None
    if origin in (list, typing.List):
        (item_ann,) = get_args(target) or (Any,)
        if not isinstance(value, list):
            raise CodecError(path, "expected an array")
        return [from_jsonable(item_ann, v, path="%s/%d" % (path, i))
                for i, v in enumerate(value)]
    if origin in (dict, typing.Dict):
        args = get_args(target)
        item_ann = args[1] if len(args) == 2 else Any
        if not isinstance(value, dict):
            raise CodecError(path, "expected an object")
        return {k: from_jsonable(item_ann, v, path="%s/%s" % (path, k))
                for k, v in value.items()}
    if dataclasses.is_dataclass(target):
        if not isinstance(value, dict):
            raise CodecError(path, "expected an object for %s" % target.__name__)
        return _build_dataclass(target, value, path)
    if target is bool:
        if not isinstance(value, bool):
            raise CodecError(path, "expected a boolean")
        return value
    if target is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise CodecError(path, "expected an integer")
        return value
    if target is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CodecError(path, "expected a number")
        return _check_number(float(value), path)
    if target is str:
        if not isinstance(value, str):
            raise CodecError(path, "expected a string")
        return value
    raise CodecError(path, "unsupported annotation %r" % (target,))


def _build_dataclass(cls: type, data: dict[str, Any], path: str) -> Any:
    hints = hints_for(cls)
    fields = dataclasses.fields(cls)
    known = {json_key(f) for f in fields}
    unknown = sorted(set(data) - known)
    if unknown:
        raise CodecError(path, "unknown field(s) for %s: %s"
                         % (cls.__name__, ", ".join(unknown)))
    kwargs: dict[str, Any] = {}
    for field in fields:
        key = json_key(field)
        child = "%s/%s" % (path, key)
        if key not in data:
            _, allows_absent, _ = _is_optional_like(hints[field.name])
            if allows_absent:
                kwargs[field.name] = ABSENT
                continue
            if field.default is not dataclasses.MISSING or \
                    field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                continue
            raise CodecError(child, "required field is missing")
        kwargs[field.name] = from_jsonable(hints[field.name], data[key],
                                           path=child)
    return cls(**kwargs)


def _check_jsonable_any(value: Any, path: str) -> Any:
    """``Any`` fields still have to hold JSON, and still reject NaN."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return _check_number(value, path)
    if isinstance(value, list):
        return [_check_jsonable_any(v, "%s/%d" % (path, i))
                for i, v in enumerate(value)]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CodecError(path, "object keys must be strings")
        return {k: _check_jsonable_any(v, "%s/%s" % (path, k))
                for k, v in value.items()}
    raise CodecError(path, "%s is not JSON data" % type(value).__name__)
