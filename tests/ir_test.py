"""Tests for the intermediate representation helpers."""

from __future__ import annotations

import pytest

from midea_lua_conformance.ir import Constant, Enum, ProtocolDefinition


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("BYTE_MODE_COOL", "MODE_COOL", id="byte_prefix"),
        pytest.param("VALUE_MODE_COOL", "MODE_COOL", id="value_prefix"),
        pytest.param("KEY_POWER", "POWER", id="key_prefix"),
        pytest.param("STR_NAME", "NAME", id="str_prefix"),
        pytest.param("ENUM_SPEED", "SPEED", id="enum_prefix"),
        pytest.param("SOME_TABLE", "SOME_TABLE", id="no_prefix"),
    ],
)
def test_constant_stem(name: str, expected: str) -> None:
    """Only the known constant prefixes are stripped."""
    assert Constant(name, 1).stem == expected


def test_enum_by_value() -> None:
    """The reverse mapping goes from protocol value to logical name."""
    enum = Enum("MODE", {"COOL": 0x02, "HEAT": "heat"})
    assert enum.by_value() == {0x02: "COOL", "heat": "HEAT"}


def test_paired_enum_skips_non_integer_bytes() -> None:
    """A ``BYTE_`` member holding a string is not a protocol byte."""
    definition = ProtocolDefinition(
        source="lua/xx/T_0000_XX_1.lua",
        enums={
            "MODE": Enum("MODE", {"COOL": 0x02, "ODD": "0x03"}),
            "MODE_VALUES": Enum("MODE_VALUES", {"COOL": "cool", "ODD": "odd"}),
        },
    )
    assert definition.paired_enum("MODE") == {0x02: "cool"}
