"""The render-time frame gate (ASM-1 §8): the parts that need no CAD kernel.

The geometry half — rendering the fixtures and testing frames against meshes — is in
test_frame_gate_geometry.py under the `geometry` marker.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hyperobjects_schemas import load as load_schema
from y4d_spec import frame_gate
from y4d_spec.frame_gate import (
    RULE_BY_GEOMETRY_TYPE,
    UNVERIFIED_GEOMETRY_TYPES,
    FrameCheck,
    check_frames,
    describe_rules,
    frame_rule,
    framed_interfaces,
    parameter_points,
)

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
FRAME_PLATE = FIXTURES / "frame-plate"
FRAME_PLATE_WRONG = FIXTURES / "frame-plate-wrong"
THIMBLE = FIXTURES / "thimble"
SRC = Path(__file__).resolve().parents[1] / "src"


def _manifest(path: Path) -> dict:
    return json.loads((path / "project.json").read_text(encoding="utf-8"))


def _geometry_type_enum() -> set[str]:
    schema = load_schema("project-manifest")
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            gt = node.get("geometry_type")
            if isinstance(gt, dict) and isinstance(gt.get("enum"), list):
                found.update(gt["enum"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return found


def test_every_schema_geometry_type_has_a_rule_or_is_declared_unverified():
    enum = _geometry_type_enum()
    assert len(enum) == 21
    covered = set(RULE_BY_GEOMETRY_TYPE) | set(UNVERIFIED_GEOMETRY_TYPES)
    assert covered == enum
    assert not set(RULE_BY_GEOMETRY_TYPE) & set(UNVERIFIED_GEOMETRY_TYPES)


def test_rule_lookup():
    assert frame_rule("bolt_pattern") == "planar"
    assert frame_rule("rail") == "planar"
    assert frame_rule("socket") == "axis"
    assert frame_rule("thread") == "axis"
    assert frame_rule("snap") is None
    assert frame_rule(None) is None


def test_framed_interfaces_only_counts_frame_objects():
    doc = _manifest(FRAME_PLATE)
    assert [i["id"] for i in framed_interfaces(doc)] == [
        "motor_face", "centre_bore", "underside", "pin_shaft", "edge_clip"]
    assert framed_interfaces(_manifest(THIMBLE)) == []
    assert framed_interfaces({}) == []
    assert framed_interfaces({"hyperobject": {"cdg_interfaces": [{"id": "a", "frame": 3}]}}) == []


def test_parameter_points_are_defaults_then_every_preset():
    doc = _manifest(FRAME_PLATE)
    points = parameter_points(doc)
    assert [p for p, _ in points] == ["defaults", "thick", "long_pin"]
    assert points[0][1] == {}
    assert points[1][1] == {"plate_thick": 6.0, "bore_d": 10.0}
    assert parameter_points(doc, presets=False) == [("defaults", {})]


def test_frame_check_summary_tiers():
    ok = FrameCheck("a", "p", "defaults", "pass", "planar", "face found")
    bad = FrameCheck("a", "p", "thick", "fail", "axis", "bore offset", {"axis_offset_mm": 1.0})
    unv = FrameCheck("a", "p", "defaults", "unverified", "none", "no rule")
    assert ok.ok and unv.ok and not bad.ok
    assert ": ok — " in ok.summary
    assert "preset 'thick'" in bad.summary and "FAIL" in bad.summary
    assert '"axis_offset_mm": 1.0' in bad.summary
    assert "UNVERIFIED" in unv.summary


def test_describe_rules_quotes_the_live_thresholds():
    text = "\n".join(describe_rules())
    assert f"{frame_gate.NORMAL_TOLERANCE_DEG:g}°" in text
    assert f"{frame_gate.PLANE_OFFSET_TOLERANCE_MM:g}mm" in text
    assert f"{frame_gate.FACE_MIN_AREA_MM2:g}mm²" in text
    assert f"{frame_gate.FACE_SEARCH_RADIUS_MM:g}mm" in text
    assert "UNVERIFIED" in text


def test_rules_command_prints_the_gate(capsys):
    from y4d_spec.cli import main

    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "FRAME GATE" in out
    assert "frames=P/M ok" in out


# ── the gate is a no-op without frames ────────────────────────────────────────
def test_no_frames_returns_empty_before_rendering(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the frame gate rendered for a frameless manifest")

    monkeypatch.setattr(frame_gate, "_PartRenderer", refuse)
    assert check_frames(THIMBLE, _manifest(THIMBLE)) == []
    assert check_frames(THIMBLE, {"hyperobject": {"cdg_interfaces": [{"id": "x"}]}}) == []


def test_no_frames_imports_no_cad_or_mesh_library():
    """A frameless manifest must not even import the kernel or the mesh library."""
    code = (
        "import json, sys\n"
        "from y4d_spec.frame_gate import check_frames\n"
        f"doc = json.load(open({str(THIMBLE / 'project.json')!r}))\n"
        f"assert check_frames({str(THIMBLE)!r}, doc) == []\n"
        "print(sorted(m for m in ('cadquery', 'trimesh', 'numpy', 'y4d_spec.frame_geometry')"
        " if m in sys.modules))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
        env={"PYTHONPATH": str(SRC)},
    )
    assert out.stdout.strip() == "[]"


def test_summary_line_has_no_frames_clause_without_frames(capsys):
    from y4d_spec.cli import main

    main(["check", str(THIMBLE)])
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert "frames=" not in line


@pytest.mark.parametrize("fixture", [FRAME_PLATE, FRAME_PLATE_WRONG])
def test_frame_fixtures_conform_statically(fixture):
    """Both fixtures are well-formed: a wrong frame is a GEOMETRY finding, which only
    the render-time gate can make."""
    from y4d_spec import check_cartridge

    result = check_cartridge(fixture)
    assert result.ok, result.problems
    assert result.frames == []  # no --render, no gate


def test_readme_states_the_gate_thresholds_the_code_uses():
    """The numbers a frame author sizes a repair against (cf. test_docs_currency)."""
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert f"within {frame_gate.NORMAL_TOLERANCE_DEG:g}°" in readme
    assert f"within {frame_gate.PLANE_OFFSET_TOLERANCE_MM:g}mm" in readme
    assert f"at least {frame_gate.FACE_MIN_AREA_MM2:g}mm²" in readme
    assert f"within {frame_gate.FACE_SEARCH_RADIUS_MM:g}mm" in readme
    assert f"fit within {frame_gate.CYLINDER_FIT_TOLERANCE_MM:g}mm" in readme
    assert f"at least {frame_gate.CYLINDER_MIN_COVERAGE_DEG:g}°" in readme
    for gtype in (*frame_gate.RULE_BY_GEOMETRY_TYPE, *frame_gate.UNVERIFIED_GEOMETRY_TYPES):
        assert f"`{gtype}`" in readme, gtype
