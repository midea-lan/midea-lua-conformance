"""Tests for the report header and rendering."""

from __future__ import annotations

import json
import shutil
import subprocess
from importlib.metadata import version
from typing import TYPE_CHECKING

import pytest

from midea_lua_conformance import report
from midea_lua_conformance.compare import Comparison, Finding, Verdict
from midea_lua_conformance.report import (
    _git_checkout_summary,
    describe_midea_local,
    render_report,
)

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run(  # noqa: S603 - fixed git arguments
        [git, "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Create a midea-local-like checkout whose last merged PR is #956."""
    (tmp_path / "midealocal").mkdir()
    (tmp_path / "midealocal" / "device.py").write_text("x = 1\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "feat(fan)!: move fan options (#956)")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "Merge branch 'main'")
    return tmp_path


def test_git_checkout_summary(checkout: Path) -> None:
    """The commit and the latest PR found in the history are reported."""
    commit = _git(checkout, "rev-parse", "--short", "HEAD")
    assert _git_checkout_summary(checkout) == (
        f"{commit}, latest merged PR "
        "[#956](https://github.com/midea-lan/midea-local/pull/956)"
    )


def test_git_checkout_summary_local_changes(checkout: Path) -> None:
    """Uncommitted changes to midealocal are flagged."""
    (checkout / "midealocal" / "device.py").write_text("x = 2\n")
    commit = _git(checkout, "rev-parse", "--short", "HEAD")
    summary = _git_checkout_summary(checkout)
    assert summary is not None
    assert summary.startswith(f"{commit} + local changes, ")


def test_git_checkout_summary_not_a_checkout(tmp_path: Path) -> None:
    """A directory outside git yields no summary instead of failing."""
    assert _git_checkout_summary(tmp_path) is None


def test_describe_midea_local_reports_installed_version() -> None:
    """The installed midea-local version is always part of the description."""
    assert describe_midea_local().startswith(f"midea-local {version('midea-local')}")


class _Distribution:
    """Installed-distribution stand-in carrying a PEP 610 ``direct_url.json``."""

    version = "14.0.0"

    def __init__(self, direct_url: dict[str, object]) -> None:
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str:
        assert filename == "direct_url.json"
        return json.dumps(self._direct_url)


def _install(monkeypatch: pytest.MonkeyPatch, direct_url: dict[str, object]) -> None:
    monkeypatch.setattr(
        report,
        "distribution",
        lambda name: _Distribution(direct_url),  # noqa: ARG005
    )


def test_git_checkout_summary_without_git(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a git executable there is no summary instead of a failure."""
    monkeypatch.setenv("PATH", "")
    assert _git_checkout_summary(checkout) is None


def test_describe_midea_local_git_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """A git install is identified by its short commit."""
    _install(
        monkeypatch,
        {
            "url": "https://github.com/midea-lan/midea-local.git",
            "vcs_info": {"vcs": "git", "commit_id": "0123456789abcdef"},
        },
    )
    assert describe_midea_local() == "midea-local 14.0.0 (0123456)"


def test_describe_midea_local_checkout(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local checkout install also reports its commit and latest merged PR."""
    _install(monkeypatch, {"url": checkout.as_uri(), "dir_info": {"editable": True}})
    commit = _git(checkout, "rev-parse", "--short", "HEAD")
    assert describe_midea_local() == (
        f"midea-local 14.0.0 ({commit}, latest merged PR "
        "[#956](https://github.com/midea-lan/midea-local/pull/956))"
    )


def test_describe_midea_local_directory_outside_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A directory install outside git falls back to the version alone."""
    _install(monkeypatch, {"url": tmp_path.as_uri(), "dir_info": {}})
    assert describe_midea_local() == "midea-local 14.0.0"


def test_render_report_without_different_or_unknown_findings() -> None:
    """Empty sections say so, and comparisons without UNKNOWN are not listed."""
    missing = Finding(Verdict.MISSING, "command", "body_type 0x22", "not sent")
    text = render_report(
        [Comparison("lua/b1/a.lua", "b1", [missing])],
        midea_local="midea-local 14.0.0",
    )
    assert "## DIFFERENT\n\n_none_\n" in text
    assert "### b1: body_type 0x22" in text
    assert text.endswith("## UNKNOWN (collapsed)\n\n\n")
