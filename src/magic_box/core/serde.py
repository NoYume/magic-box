"""JSON-lines serialization for the data contracts.

Owner: Nikhil
"""

import dataclasses
import json
import types
import typing
from typing import Any, Union

from magic_box.core import contracts

SERIALIZABLE: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        contracts.Push,
        contracts.PlayerState,
        contracts.VoiceEvent,
        contracts.Action,
        contracts.GameEvent,
        contracts.SpellView,
        contracts.PlayerView,
        contracts.ProjectileView,
        contracts.GameView,
        contracts.VoiceConfig,
    )
}


def _encode(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, frozenset):
        return sorted(_encode(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    return value


def to_json(obj: Any) -> str:
    """Serialize a contract dataclass to a single JSON line (no trailing newline)."""
    name = type(obj).__name__
    if SERIALIZABLE.get(name) is not type(obj):
        raise ValueError(f"{name} is not serializable")
    return json.dumps({"type": name, "data": _encode(obj)}, separators=(",", ":"))


def _decode(value: Any, hint: Any) -> Any:
    if hint is Any:
        return value
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is Union or origin is types.UnionType:
        if value is None:
            return None
        non_none = [a for a in args if a is not type(None)]
        return _decode(value, non_none[0])
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(v, args[0]) for v in value)
        return tuple(_decode(v, a) for v, a in zip(value, args, strict=True))
    if origin is frozenset:
        return frozenset(_decode(v, args[0]) for v in value)
    if origin is dict:
        key_hint, val_hint = args
        return {_decode_key(k, key_hint): _decode(v, val_hint) for k, v in value.items()}
    if dataclasses.is_dataclass(hint):
        return _build(hint, value)
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _decode_key(key: str, hint: Any) -> Any:
    return int(key) if hint is int else key


def _build(cls: type, data: dict[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    return cls(
        **{
            f.name: _decode(data[f.name], hints[f.name])
            for f in dataclasses.fields(cls)
            if f.name in data
        }
    )


def from_json(line: str) -> Any:
    """Rebuild a contract dataclass from a line written by to_json."""
    envelope = json.loads(line)
    name = envelope.get("type")
    cls = SERIALIZABLE.get(name)
    if cls is None:
        raise ValueError(f"unknown type {name!r}")
    return _build(cls, envelope["data"])
