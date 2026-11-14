"""Tests for the pre-commit hook that scopes the comparison to touched files."""

from __future__ import annotations

import re
import runpy
import sys
from pathlib import Path

import pytest

from midea_lua_conformance import precommit_check
from midea_lua_conformance.mapping import DEVICES_ROOT, LUA_ROOT
from midea_lua_conformance.precommit_check import main

_REPO_ROOT = LUA_ROOT.parent
# Reports name lua files with the platform path separator.
_E1_LUA = sorted(
    str(Path("lua", "e1", p.name)) for p in (LUA_ROOT / "e1").glob("*.lua")
)
_AC_LUA = str(Path("lua", "ac", "T_0000_AC_00000Q11_2023072401.lua"))
_COMPARED = re.compile(r"^\[lua-conformance\] (\S+) vs (\S+): ", re.MULTILINE)


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        pytest.param([], [], id="no_files"),
        pytest.param(["lua/e1/T_0000_E1_deleted.lua"], [], id="deleted_file"),
        pytest.param(["README.md"], [], id="outside_device_trees"),
        pytest.param(["lua/e7/T_0000_E7_5.lua"], [], id="lua_without_package"),
        pytest.param([_AC_LUA], [(_AC_LUA, "ac")], id="lua_changed"),
        pytest.param(
            [str(DEVICES_ROOT / "e1" / "message.py"), _E1_LUA[0]],
            [(lua, "e1") for lua in _E1_LUA],
            id="python_changed_compares_every_lua_file",
        ),
    ],
)
def test_touched_files_are_compared(
    files: list[str],
    expected: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only matched device types touched by the commit are compared."""
    monkeypatch.chdir(_REPO_ROOT)

    assert main(files) == 0

    assert _COMPARED.findall(capsys.readouterr().out) == expected


def test_verified_device_regression_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A verified device gaining a MISSING field fails the commit."""
    lua = tmp_path / "e1" / "T_0000_E1_99.lua"
    lua.parent.mkdir()
    lua.write_text(
        "local BYTE_DEVICE_TYPE = 0xE1\n"
        "function updateGlobalPropertyValueByByte(messageBytes)\n"
        "    weirdSensorValue = messageBytes[40]\n"
        "end\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(precommit_check, "LUA_ROOT", tmp_path)

    assert main([str(lua)]) == 1

    captured = capsys.readouterr()
    assert "  VERIFIED_DEVICES regression in 'e1':\n" in captured.out
    assert "[MISSING] decode_field: weird_sensor" in captured.out
    assert "a VERIFIED_DEVICES type gained a structural" in captured.err


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Running the module directly exits with the hook result."""
    monkeypatch.setattr(sys, "argv", ["precommit_check"])
    monkeypatch.delitem(sys.modules, "midea_lua_conformance.precommit_check")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("midea_lua_conformance.precommit_check", run_name="__main__")

    assert exc_info.value.code == 0
