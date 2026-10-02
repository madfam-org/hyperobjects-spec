"""default-drift — manifest `default` vs the literal the source falls back to.

NOTE ONLY: every test that runs the rule through `check_cartridge` also asserts the
cartridge stays `ok`. A rule that fails a cartridge before its false-positive analysis
is written down is the thing AGENTS.md outlaws.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from y4d_spec import check_cartridge
from y4d_spec.default_drift import (
    RULE_ID,
    cadquery_param_literals,
    default_drift_findings,
    defaults_equal,
    graph_binding_literals,
    scad_top_level_literals,
)

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"


# ── comparison ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "manifest, source, equal",
    [
        (True, 1, True),
        (False, 0, True),
        (True, 0, False),
        (1, True, True),
        (2, 2.0, True),
        (0.3, 0.30000000001, True),  # within 1e-9
        (0.3, 0.3001, False),
        ("4", 4, True),  # a select spelled "4" vs the int the script casts
        ("light", "gopro", False),
        ("ISO", "iso", False),  # strings as-is: no case folding
        ("a ", "a", False),  # … and no trimming
        ("light", 1, False),
    ],
)
def test_defaults_equal(manifest, source, equal):
    assert defaults_equal(manifest, source) is equal


# ── CadQuery / FC: PARAM(lambda: id, literal) ────────────────────────────────
CQ_SOURCE = '''"""Docstring quoting the idiom: PARAM(lambda: name, default) and
PARAM(lambda: wall, 99) must not count."""
LIP = 1.5


def PARAM(getter, default):
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


wall = float(PARAM(lambda: wall, 2.0))   # PARAM(lambda: wall, 77) in a comment
neg = float(PARAM(lambda: neg, -2.5))
lip = float(PARAM(lambda: lip, LIP))
flag = bool(PARAM(lambda: flag, True))
label = str(PARAM(lambda: label, "gopro"))
expr = float(PARAM(lambda: expr, wall * 2))
other = PARAM(lambda x: x, 3)


def per_part():
    return float(PARAM(lambda: wall, 3.0))
'''


def test_cadquery_literals_are_read_with_ast():
    found = cadquery_param_literals(CQ_SOURCE)
    assert [(i, v) for i, v, _ in found] == [
        ("wall", 2.0),
        ("neg", -2.5),
        ("lip", 1.5),
        ("flag", True),
        ("label", "gopro"),
        ("wall", 3.0),
    ]
    lines = {(i, v): line for i, v, line in found}
    assert CQ_SOURCE.splitlines()[lines[("wall", 2.0)] - 1].startswith("wall = ")


def test_unparseable_cadquery_yields_nothing():
    assert cadquery_param_literals("def broken(:\n") == []


# ── OpenSCAD: top-level <id> = <literal>; ────────────────────────────────────
SCAD_SOURCE = """// header
/* block
   comment: wall = 99; */
include <inc.scad>
use <lib.scad>
wall = 2.5; // [1:5] customizer hint
flag = true;
label = "a;b{c}";
count = 3; size = 1e2;
derived = wall * 2;
N = is_undef(N) ? 7 : N;

module body() {
    wall = 42;
    cube(wall);
}

if (flag) { inner = 5; }
after_block = -0.5;
wall = 2.75;
"""


def test_scad_top_level_literals():
    found = scad_top_level_literals(SCAD_SOURCE)
    pairs = [(i, v) for i, v, _ in found]
    assert pairs == [
        ("wall", 2.5),
        ("flag", True),
        ("label", "a;b{c}"),
        ("count", 3),
        ("size", 100.0),
        ("N", 7),
        ("after_block", -0.5),
        ("wall", 2.75),
    ]
    lines = SCAD_SOURCE.splitlines()
    for ident, _, line in found:
        assert lines[line - 1].lstrip().startswith(ident) or f"; {ident}" in lines[line - 1], (
            ident, line
        )


def test_scad_line_numbers_survive_directives_and_block_comments():
    line = {i: n for i, _, n in scad_top_level_literals(SCAD_SOURCE)}
    assert line["flag"] == 7
    assert line["after_block"] == 19


# ── graph ────────────────────────────────────────────────────────────────────
def test_graph_binding_literals():
    graph = {"nodes": [{"id": "outline", "type": "profile_circle", "params": {"r": 45}},
                       {"id": "plate", "type": "extrude", "params": {"height": 8}}]}
    manifest = {"parameters": [
        {"id": "radius", "default": 40, "binding": "outline.r"},
        {"id": "height", "default": 8, "binding": ["plate.height", "missing.height"]},
        {"id": "loose", "default": 1},
    ]}
    assert graph_binding_literals(graph, manifest) == [
        ("radius", 45, "outline.r"),
        ("height", 8, "plate.height"),
    ]


# ── the rule over a cartridge directory ──────────────────────────────────────
def _cartridge(root: Path) -> Path:
    cart = root / "drifty"
    (cart / "lib").mkdir(parents=True)
    (cart / "main.py").write_text(
        "def PARAM(g, d):\n    return d\n"
        "length = float(PARAM(lambda: length, 150))\n"
        "wall = float(PARAM(lambda: wall, 2.0))\n"
        "flag = bool(PARAM(lambda: flag, 1))\n",
        encoding="utf-8",
    )
    (cart / "a.scad").write_text(
        "include <lib/common.scad>\nlength = 100;\nshared = 9;\ncube(length);\n",
        encoding="utf-8",
    )
    (cart / "lib" / "common.scad").write_text("wall = 3;\n", encoding="utf-8")
    (cart / "g.graph.json").write_text(
        json.dumps({"nodes": [{"id": "n", "type": "box", "params": {"w": 11}}]}),
        encoding="utf-8",
    )
    manifest = {
        "modes": [
            {"id": "cq", "cq_file": "main.py"},
            {"id": "cq2", "cq_file": "main.py"},
            {"id": "scad", "scad_file": "a.scad"},
            {"id": "graph", "scad_file": "g.graph.json"},
        ],
        "parameters": [
            {"id": "length", "default": 100},
            {"id": "wall", "default": 2},
            {"id": "flag", "default": True},
            {"id": "shared", "default": 1, "visible_in_modes": ["cq"]},  # out of scope
            {"id": "width", "default": 10, "binding": "n.w", "modes": ["graph"]},
            {"id": "nodefault"},
        ],
    }
    (cart / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cart


def test_findings_are_per_file_line_with_the_modes_that_use_it(tmp_path):
    cart = _cartridge(tmp_path)
    manifest = json.loads((cart / "project.json").read_text())
    findings = default_drift_findings(cart, manifest)
    table = {(f.file, f.param): f for f in findings}
    assert set(table) == {
        ("main.py", "length"),
        ("lib/common.scad", "wall"),
        ("g.graph.json", "width"),
    }
    cq = table[("main.py", "length")]
    assert cq.modes == ("cq", "cq2") and cq.line == 3
    assert (cq.manifest_default, cq.source_literal, cq.engine) == (100, 150, "cadquery")
    scad = table[("lib/common.scad", "wall")]
    assert scad.modes == ("scad",) and scad.line == 1 and scad.engine == "openscad"
    graph = table[("g.graph.json", "width")]
    assert (graph.source_literal, graph.engine) == (11, "graph")
    # `shared` differs (9 vs 1) but is scoped away from the scad mode: GOC-1 §4.1
    # never injects it there, so it is not this rule's business.
    assert all(f.param != "shared" for f in findings)


def test_the_rule_is_a_note_and_never_a_failure(tmp_path):
    cart = _cartridge(tmp_path)
    result = check_cartridge(cart)
    drift = [n for n in result.notes if n.startswith(f"{RULE_ID}:")]
    assert len(drift) == 3
    assert not any(RULE_ID in p for p in result.problems)


def test_soft_script_file_modes_are_read_too(tmp_path):
    cart = tmp_path / "garment"
    cart.mkdir()
    (cart / "main.py").write_text("head = float(PARAM(lambda: head_girth, 580.0))\n")
    manifest = {"modes": [{"id": "set", "script_file": "main.py"}],
                "parameters": [{"id": "head_girth", "default": 570}]}
    (f,) = default_drift_findings(cart, manifest)
    assert (f.engine, f.source_literal, f.manifest_default) == ("fc", 580.0, 570)


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()))
def test_the_shipped_fixtures_carry_no_drift(name):
    cart = FIXTURES / name
    manifest = json.loads((cart / "project.json").read_text(encoding="utf-8"))
    assert default_drift_findings(cart, manifest) == []


def test_rules_listing_names_the_rule(capsys):
    from y4d_spec.cli import main

    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "default_drift_rules" in out and "NOTE ONLY" in out
