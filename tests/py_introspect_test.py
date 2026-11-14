"""Unit tests for ``midealocal`` device introspection."""

from __future__ import annotations

import ast
import sys
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from midea_lua_conformance.ir import DecodeField
from midea_lua_conformance.py_introspect import (
    _extract_decode_fields_from_ast,
    _parser_field,
    introspect_device,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_introspect_e1_decode_fields() -> None:
    """AST analysis recovers the E1 response-body field map with masks."""
    py = introspect_device("e1")
    assert py.device_type == 0xE1

    by_name = {f.name: f for f in py.decode_fields}
    assert by_name["status"].signature() == (1, 0xFF, 0)
    assert by_name["mode"].signature() == (2, 0xFF, 0)
    assert by_name["child_lock"].signature() == (5, 0x10, 0)
    assert by_name["temperature"].signature() == (11, 0xFF, 0)
    assert by_name["door"].boolean is True


@pytest.mark.parametrize(
    ("name", "found"),
    [
        pytest.param("status", True, id="exact"),
        pytest.param("STATUS", True, id="case_insensitive"),
        pytest.param("no_such_field", False, id="unknown"),
    ],
)
def test_decode_field_lookup(name: str, found: bool) -> None:
    """Decode fields are looked up by name, ignoring case."""
    field = introspect_device("e1").decode_field(name)
    assert (field is not None) is found


def test_introspect_e1_enums_from_class_vars() -> None:
    """Class-level lookup tables (``_modes`` / ``_status``) lower into enums."""
    py = introspect_device("e1")
    modes = py.enum("modes")
    assert modes is not None
    assert modes.members["eco_wash"] == 0x04
    status = py.enum("status")
    assert status is not None
    assert status.members["running"] == 0x03


def test_introspect_e1_request_bytes() -> None:
    """Request classes are instantiated and their body bytes captured."""
    py = introspect_device("e1")
    by_name = {c.name: c for c in py.commands}
    assert by_name["MessageQuery"].body_type == 0x00
    assert by_name["MessageLock"].body_type == 0x83
    # MessageLock default body: [0x83, 0x04, 0x00 * 36]  (0x04 == "unlocked")
    assert by_name["MessageLock"].body[1] == 0x04


def test_introspect_unknown_package_is_soft_failure() -> None:
    """An unknown device folder yields notes, not an exception."""
    py = introspect_device("zz")
    assert py.device_type is None
    assert py.notes


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "BoolParser(DeviceAttributes.power, 1, bit=0)",
            DecodeField("power", 1, 0x01, 0, boolean=True),
            id="bool_bit_keyword",
        ),
        pytest.param(
            'BoolParser("power", 1, 3)',
            DecodeField("power", 1, 0x08, 3, boolean=True),
            id="bool_bit_positional",
        ),
        pytest.param(
            "IntParser(DeviceAttributes.fan_speed, 3, byte_mask=0x7F)",
            DecodeField("fan_speed", 3, 0x7F, 0),
            id="int_byte_mask_not_shifted",
        ),
        pytest.param(
            "IntParser('target', 4, 100)",
            DecodeField("target", 4, 0xFF, 0),
            id="int_third_positional_is_max_value",
        ),
        pytest.param(
            "FloatParser('indoor_temperature', 7, 2, transform_func=parse_temp)",
            DecodeField(
                "indoor_temperature",
                7,
                0xFF,
                0,
                transform="2 bytes; parse_temp",
            ),
            id="float_multi_byte_with_transform",
        ),
    ],
)
def test_parser_declarations_become_decode_fields(
    source: str,
    expected: DecodeField,
) -> None:
    """Midealocal BodyParser declarations lower to the same IR as body[...] reads."""
    call = ast.parse(source, mode="eval").body
    assert isinstance(call, ast.Call)
    assert _parser_field(call) == expected


def test_non_parser_call_is_ignored() -> None:
    """Only the known parser classes are lowered."""
    call = ast.parse("SomethingElse('power', 1)", mode="eval").body
    assert isinstance(call, ast.Call)
    assert _parser_field(call) is None


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("IntParser(attribute_name, 1)", id="name_not_a_literal"),
        pytest.param("IntParser('target', -offset)", id="byte_not_a_literal"),
    ],
)
def test_parser_without_literal_name_or_byte_is_ignored(source: str) -> None:
    """A field is only lowered when its name and byte are known statically."""
    call = ast.parse(source, mode="eval").body
    assert isinstance(call, ast.Call)
    assert _parser_field(call) is None


def test_unprintable_body_read_has_no_transform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body read whose expression cannot be printed still yields its field."""
    message_py = tmp_path / "message.py"
    message_py.write_text(
        "class MessageBody:\n"
        "    def __init__(self, body):\n"
        "        self.power = body[3] & 0x01\n",
        encoding="utf-8",
    )

    def _fail(node: ast.AST) -> str:
        raise ValueError(node)

    monkeypatch.setattr(ast, "unparse", _fail)

    [field] = _extract_decode_fields_from_ast(message_py)
    assert field.signature() == (3, 0x01, 0)
    assert field.transform is None


def test_introspect_package_without_device_type_or_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A device package without a DeviceType member or message module is noted."""
    monkeypatch.setitem(
        sys.modules,
        "midealocal.devices.zz",
        ModuleType("midealocal.devices.zz"),
    )

    py = introspect_device("zz")
    assert py.device_type is None
    assert py.decode_fields == []
    assert py.notes[0] == "no DeviceType member for 'zz'"
    assert py.notes[1].startswith("message import failed: ")


def test_introspect_parser_based_package() -> None:
    """A package declaring its fields with parsers is no longer empty."""
    by_name = {(f.name, f.byte): f for f in introspect_device("ac").decode_fields}
    assert by_name["power", 1].signature() == (1, 0x01, 0)
    assert by_name["swing_horizontal", 7].signature() == (7, 0x03, 0)
