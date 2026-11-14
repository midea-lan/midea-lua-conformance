"""Tests for the LUA <-> ``midealocal`` mapping logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from midea_lua_conformance import mapping
from midea_lua_conformance.mapping import (
    DeviceMapping,
    MatchStatus,
    build_mapping,
    matched_packages,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module")
def rows() -> list[DeviceMapping]:
    """Return the full mapping, built once for the module."""
    return build_mapping()


def test_every_device_type_is_classified(rows: list[DeviceMapping]) -> None:
    """Every row has a status and at least one piece of evidence."""
    assert rows
    for row in rows:
        assert isinstance(row.status, MatchStatus)
        assert row.evidence


def test_matched_rows_have_both_sides_and_corroboration(
    rows: list[DeviceMapping],
) -> None:
    """A MATCHED row points at a real lua dir and package with real evidence."""
    matched = [r for r in rows if r.status is MatchStatus.MATCHED]
    assert len(matched) > 20
    for row in matched:
        assert row.lua_dir
        assert row.py_package
        assert row.lua_files
        assert any("DeviceType" in ev or "type token" in ev for ev in row.evidence)


def test_no_unexplained_conflicts(rows: list[DeviceMapping]) -> None:
    """A CONFLICT would mean same-named dirs disagree on the device byte."""
    conflicts = [r for r in rows if r.status is MatchStatus.CONFLICT]
    assert conflicts == [], [r.key for r in conflicts]


def test_known_unmatched_are_reported_not_guessed(rows: list[DeviceMapping]) -> None:
    """Lua-only and Python-only device types surface as UNMATCHED."""
    by_key = {r.key: r for r in rows}
    # e7 has a lua/ dir but no midealocal/devices/e7 package
    assert by_key["e7"].status is MatchStatus.UNMATCHED_NO_PYTHON
    # x34 has a package but no lua/ dir
    assert by_key["x34"].status is MatchStatus.UNMATCHED_NO_LUA


def test_e1_maps_cleanly(rows: list[DeviceMapping]) -> None:
    """The reference device (E1) maps in both directions."""
    e1 = next(r for r in rows if r.key == "e1")
    assert e1.status is MatchStatus.MATCHED
    assert e1.device_type == 0xE1
    assert any(f.startswith("T_0000_E1_") for f in e1.lua_files)


def test_matched_packages(rows: list[DeviceMapping]) -> None:
    """Only the MATCHED keys are returned, in mapping order."""
    assert matched_packages() == [
        r.key for r in rows if r.status is MatchStatus.MATCHED
    ]


def test_device_type_byte_disagreement_is_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Lua BYTE_DEVICE_TYPE that disagrees with DeviceType is surfaced."""
    lua_dir = tmp_path / "e1"
    lua_dir.mkdir()
    (lua_dir / "T_0000_E1_1.lua").write_text(
        "local BYTE_DEVICE_TYPE = 0xE2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mapping, "LUA_ROOT", tmp_path)

    e1 = next(r for r in build_mapping() if r.key == "e1")
    assert e1.evidence == [
        "CONFLICT: lua BYTE_DEVICE_TYPE=0xE2 != DeviceType.E1=0xE1",
        "filename type token 'e1' == DeviceType byte 0xE1",
    ]
    # the filename token still corroborates the pairing
    assert e1.status is MatchStatus.MATCHED
