"""Tests for the ``python -m midea_lua_conformance`` entry point."""

from __future__ import annotations

import runpy
import sys
from typing import TYPE_CHECKING

import pytest

from midea_lua_conformance import run

if TYPE_CHECKING:
    from pathlib import Path


def test_module_entry_point_runs_the_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running the package as a module regenerates the reports."""
    monkeypatch.setattr(run, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["midea_lua_conformance", "--limit-per-dir", "0"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("midea_lua_conformance", run_name="__main__")

    assert exc_info.value.code == 0
    assert (tmp_path / "REPORT.md").exists()
