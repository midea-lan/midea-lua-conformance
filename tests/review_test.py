"""Tests for the generated discrepancies review."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from midea_lua_conformance.compare import Comparison, Finding, Verdict
from midea_lua_conformance.ir import DecodeField
from midea_lua_conformance.mapping import DeviceMapping, MatchStatus
from midea_lua_conformance.review import build_review, classify, render_review
from midea_lua_conformance.triage import DECISIONS, Category


def _enum(verdict: Verdict, lua: str, py: str | None = None) -> Finding:
    return Finding(verdict, "enum", "mode[0x06]", "", lua_label=lua, py_label=py)


def _decode(
    verdict: Verdict,
    lua: DecodeField,
    py: DecodeField | None = None,
    name: str = "power",
) -> Finding:
    return Finding(verdict, "decode_field", name, "", lua_field=lua, py_field=py)


@pytest.mark.parametrize(
    ("package", "finding", "expected"),
    [
        pytest.param(
            "b0",
            _enum(Verdict.DIFFERENT, "hot_steam", "host_steam"),
            Category.BUG,
            id="enum_typo",
        ),
        pytest.param(
            "b0",
            _enum(Verdict.DIFFERENT, "fast_baking", "baking"),
            Category.VOCABULARY,
            id="enum_vocabulary",
        ),
        pytest.param(
            "b0",
            _enum(Verdict.MISSING, "baking"),
            Category.BUG,
            id="enum_missing_value",
        ),
        pytest.param(
            "b1",
            Finding(Verdict.MISSING, "command", "body_type 0x22", ""),
            Category.COMMAND,
            id="command_missing",
        ),
        pytest.param(
            "ea",
            _decode(Verdict.DIFFERENT, DecodeField("t", 20), DecodeField("t", 60)),
            Category.OFFSET,
            id="decode_offset",
        ),
        pytest.param(
            "b6",
            _decode(
                Verdict.DIFFERENT,
                DecodeField("p", 3, 0x0F),
                DecodeField("p", 3, 0xFF),
            ),
            Category.MASK,
            id="decode_mask",
        ),
        pytest.param(
            "da",
            _decode(
                Verdict.DIFFERENT,
                DecodeField("r", 5, 0xFF, 4),
                DecodeField("r", 5, 0xF0, 4),
            ),
            Category.FRAMEWORK,
            id="decode_equivalent_shift",
        ),
        pytest.param(
            "fa",
            _decode(Verdict.MISSING, DecodeField("modeValue", 3), name="mode"),
            Category.FRAMEWORK,
            id="decode_missing_known_attribute",
        ),
        pytest.param(
            "b1",
            _decode(Verdict.MISSING, DecodeField("hour", 9), name="hour"),
            Category.UNPARSED,
            id="decode_missing_unparsed",
        ),
        pytest.param(
            "b6",
            _decode(Verdict.DIFFERENT, DecodeField("p", 3)),
            Category.BUG,
            id="decode_different_without_python_field",
        ),
        pytest.param(
            "b1",
            Finding(Verdict.DIFFERENT, "framing", "header_length", ""),
            Category.BUG,
            id="other_area",
        ),
    ],
)
def test_classify(package: str, finding: Finding, expected: Category) -> None:
    """Each rule sorts its kind of finding into the expected category."""
    assert classify(package, finding)[0] is expected


def test_build_review_merges_lua_files_and_applies_decisions() -> None:
    """A finding repeated over Lua files is one entry; a recorded decision wins."""
    vocabulary = Finding(
        Verdict.DIFFERENT,
        "enum",
        "mode[0x00]",
        "",
        lua_label="neutral_gear",
        py_label="none",
    )
    comparisons = [
        Comparison("lua/e1/a.lua", "e1", [vocabulary]),
        Comparison("lua/e1/b.lua", "e1", [vocabulary]),
    ]
    [entry] = build_review(comparisons)
    assert entry.lua_files == 2
    assert entry.recorded
    assert entry.reason == DECISIONS["e1", "enum", "mode[0x00]"].note


def test_render_review() -> None:
    """The review has its header, every section and the resolved decisions."""
    text = render_review(
        [],
        [],
        generated_at=datetime(2026, 10, 28, 9, 30, 15, tzinfo=UTC),
        midea_local="midea-local 14.0.0",
    )
    lines = text.splitlines()
    assert (
        lines[0] == "_Generated on 2026-10-28 09:30:15 UTC against midea-local 14.0.0_"
    )
    for section in "ABCDEFGH":
        assert f"## {section}. " in text
    # with no findings at all, every recorded decision is reported as resolved
    resolved = text.split("## Resolved since the last review", 1)[1]
    assert resolved.count("\n- `") == len(DECISIONS)


def test_render_review_sorts_findings_into_sections() -> None:
    """Each category is rendered in its own section and table style."""
    offset_note = DECISIONS["ea", "decode_field", "top_temperature"].note
    comparisons = [
        Comparison(
            "lua/b0/a.lua",
            "b0",
            [
                Finding(Verdict.MATCH, "identity", "device_type", ""),
                Finding(Verdict.UNKNOWN, "extractor", "unparsed", "no jsonToData()"),
                Finding(
                    Verdict.DIFFERENT,
                    "enum",
                    "mode[0x01]",
                    "",
                    lua_label="hot_steam",
                    py_label="host_steam",
                ),
                Finding(
                    Verdict.DIFFERENT,
                    "enum",
                    "mode[0x02]",
                    "",
                    lua_label="fast_baking",
                    py_label="baking",
                ),
                Finding(Verdict.MISSING, "framing", "header", "length a|b"),
            ],
        ),
        Comparison(
            "lua/ea/a.lua",
            "ea",
            [
                _decode(
                    Verdict.DIFFERENT,
                    DecodeField("t", 20),
                    DecodeField("t", 60),
                    name="temp",
                ),
                Finding(Verdict.DIFFERENT, "decode_field", "top_temperature", ""),
                _decode(
                    Verdict.DIFFERENT,
                    DecodeField("p", 3, 0x0F),
                    DecodeField("p", 3, 0xFF),
                    name="level",
                ),
                _decode(
                    Verdict.DIFFERENT,
                    DecodeField("r", 5, 0xFF, 4),
                    DecodeField("r", 5, 0xF0, 4),
                    name="speed",
                ),
                _decode(Verdict.DIFFERENT, DecodeField("f", 7), name="flow"),
                Finding(Verdict.MISSING, "command", "body_type 0x22", ""),
                _decode(Verdict.MISSING, DecodeField("hour", 9), name="hour"),
            ],
        ),
    ]
    mapping = [
        DeviceMapping("e7", MatchStatus.UNMATCHED_NO_PYTHON),
        DeviceMapping("x34", MatchStatus.UNMATCHED_NO_LUA),
    ]

    text = render_review(comparisons, mapping, midea_local="midea-local 14.0.0")

    assert (
        "Run scope: 2 comparisons. Totals — MATCH 1, MISSING 3, DIFFERENT 7, "
        "UNKNOWN 1; 10 distinct findings reviewed below."
    ) in text
    assert (
        "| `b0` | enum `mode[0x01]` | `hot_steam` | `host_steam` | 1 "
        "| names differ by a letter or two: likely a typo |"
    ) in text
    assert "| `b0` | framing `header` | - | - | 1 | length a\\|b |" in text
    assert "| `ea` | decode_field `flow` | `byte[7] & 0xFF >> 0` | - | 1 |  |" in text
    assert (
        "| `b0` | enum `mode[0x02]` | `fast_baking` | `baking` | 1 "
        "| same protocol value, different name |"
    ) in text
    assert f"| `ea` | +40 | `temp` 20→60 | **recorded:** {offset_note} |" in text
    assert (
        "| `ea` | decode_field `level` | `byte[3] & 0x0F >> 0` "
        "| `byte[3] & 0xFF >> 0` | 1 | same byte, different mask or shift |"
    ) in text
    assert (
        "_same bits: whole byte >> N vs (byte & top bits) >> N_\n\n"
        "- `ea` (1): `speed`\n"
    ) in text
    assert "UNKNOWN findings (not auto-verifiable) by area: extractor 1" in text
    assert "- 1 Lua device types have no midealocal package: `e7`" in text
    assert "- 1 midealocal packages have no Lua: `x34`" in text
    commands, unparsed = text.split("## H. ", 1)
    assert "- `ea` (1): `body_type 0x22`" in commands.split("## G. ", 1)[1]
    assert "- `ea` (1): `hour`" in unparsed
