"""Wrapper graphs in the keystone (RFC 0067 G-1): one `script` node, verified as its script.

Two halves. The no-render rules (`graph_core_rules`) run in seconds with no CAD kernel and
are what a commons CI meets first: the core validates the 1.2 graph, the source digest
catches a script edited without regenerating its wrapper, the declarations must equal the
manifest the graph generates, and the wrapper must wrap its own mode. The render half
(`--render --parity`) lowers the wrapper to its source and requires the two meshes to be
identical byte for byte.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from y4d_spec.graph_core_rules import graph_core_rules
from y4d_spec.graph_render import GraphError, graph_script_path, transpile_graph, wrapper_for

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
WRAPPER = FIXTURES / "graph-wrapper"
WRAPPER_SCAD = FIXTURES / "graph-wrapper-scad"


def manifest_of(cartridge: Path) -> dict:
    return json.loads((cartridge / "project.json").read_text(encoding="utf-8"))


@pytest.fixture
def scratch(tmp_path) -> Path:
    target = tmp_path / "graph-wrapper"
    shutil.copytree(WRAPPER, target)
    return target


def rewrite(path: Path, edit) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ── No-render rules ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cartridge", [WRAPPER, WRAPPER_SCAD], ids=lambda p: p.name)
def test_the_wrapper_fixtures_are_clean(cartridge):
    assert graph_core_rules(cartridge, manifest_of(cartridge)) == ([], [])


def test_existing_graph_fixtures_produce_no_core_notes():
    for name in ("graph-block", "graph-twin", "graph-twin-expr"):
        assert graph_core_rules(FIXTURES / name, manifest_of(FIXTURES / name)) == ([], [])


def test_a_script_edited_after_its_wrapper_is_source_drift(scratch):
    with (scratch / "block.py").open("a") as fh:
        fh.write("\n# edited after the wrapper was generated\n")
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert sum("[source-drift]" in p for p in problems) == 2  # both graphs list it


def test_a_manifest_that_drifted_from_its_graph(scratch):
    rewrite(scratch / "project.json",
            lambda m: m["parameters"][0].update(max=99.0))
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("block_size differs from the manifest's" in p for p in problems)


def test_a_manifest_entry_no_graph_declares(scratch):
    rewrite(scratch / "project.json", lambda m: m["presets"].append(
        {"id": "orphan", "label": {"en": "Orphan"}, "values": {"block_size": 5.0}}))
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("id:orphan is declared by no graph" in p for p in problems)


def test_a_wrapper_that_wraps_another_source(scratch):
    shutil.copy(scratch / "block.py", scratch / "other.py")

    def retarget(doc):
        doc["nodes"][0]["params"]["source"] = "other.py"
        doc["provenance"]["sources"][0]["path"] = "other.py"

    rewrite(scratch / "block.graph.json", retarget)
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("the wrapper runs 'other.py'" in p for p in problems)


def test_a_wrapper_missing_a_part_or_outputting_a_stray_one(scratch):
    rewrite(scratch / "plate.graph.json",
            lambda d: d.update(outputs={"lid": "body"}))
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("renders ['plate'], which the wrapper does not output" in p for p in problems)
    assert any("outputs ['lid'], which no mode" in p for p in problems)


def test_a_core_refusal_on_a_1_2_graph_is_a_failure(scratch):
    rewrite(scratch / "block.graph.json",
            lambda d: d["nodes"][0]["params"]["bind"].pop("hollow"))
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("hollow" in p and "[dead-parameter]" in p for p in problems)


def test_a_core_finding_on_a_1_1_graph_is_only_a_note(tmp_path):
    target = tmp_path / "graph-twin-expr"
    shutil.copytree(FIXTURES / "graph-twin-expr", target)
    graph = next(target.glob("*.graph.json"))
    rewrite(graph, lambda d: d["parameters"].update(unread={"default": 1}))
    problems, notes = graph_core_rules(target, manifest_of(target))
    assert problems == []
    assert any(n.startswith("graph-core:") and "unread" in n for n in notes)


def test_a_pass_through_does_not_keep_a_dead_parameter_alive(scratch):
    """G-DEADPARAM must still fire when a wrapper passes a parameter the script never
    reads: a generated wrapper passes everything through, so counting the pass-through
    as a reference would switch the rule off across the commons."""
    from y4d_spec.structure import dead_parameter_rules

    ghost = {"id": "ghost", "type": "slider", "default": 1.0, "min": 0.0, "max": 2.0,
             "step": 0.1, "label": {"en": "Ghost"}}

    def add_ghost(doc):
        doc["declarations"]["parameters"].append(ghost)
        doc["nodes"][0]["params"]["bind"]["ghost"] = {"param": "ghost"}

    rewrite(scratch / "block.graph.json", add_ghost)
    rewrite(scratch / "plate.graph.json", add_ghost)
    rewrite(scratch / "project.json", lambda m: m["parameters"].append(ghost))
    assert any("'ghost'" in p for p in dead_parameter_rules(scratch, manifest_of(scratch)))


@pytest.mark.parametrize("bind, needle", [
    ({"block_size": {"param": "plate_h"}}, "binds 'block_size'"),       # renamed
    ({"extra": 3.0}, "binds 'extra'"),                                   # added literal
    ({"half": {"expr": "1 / 2"}}, "binds 'half'"),                       # added expression
])
def test_a_wrapper_binds_only_pass_throughs_under_their_own_names(scratch, bind, needle):
    rewrite(scratch / "block.graph.json",
            lambda d: d["nodes"][0]["params"]["bind"].update(bind))
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any(needle in p for p in problems), problems


def test_a_wrapper_must_pass_every_mode_parameter(scratch):
    def drop(doc):
        doc["nodes"][0]["params"]["bind"].pop("finish")
        doc["declarations"]["parameters"] = [
            p for p in doc["declarations"]["parameters"] if p["id"] != "finish"]
        doc["declarations"]["parameter_groups"] = [
            g for g in doc["declarations"]["parameter_groups"] if g["id"] != "finish"] or None
        if doc["declarations"]["parameter_groups"] is None:
            del doc["declarations"]["parameter_groups"]
        doc["declarations"]["presets"] = [
            p for p in doc["declarations"]["presets"] if "finish" not in p["values"]]

    rewrite(scratch / "block.graph.json", drop)
    problems, _ = graph_core_rules(scratch, manifest_of(scratch))
    assert any("does not pass ['finish'] through" in p for p in problems), problems


def test_unreadable_graph_is_a_note_and_notes_are_not_repeated_per_mode(tmp_path):
    from y4d_spec.graph_core_rules import graph_core_rules as rules

    src = Path(__file__).parent / "fixtures" / "graph-core" / "solid-commons" / "idler-608"
    target = tmp_path / "idler-608"
    shutil.copytree(src, target)
    rewrite(target / "idler.graph.json",
            lambda d: d["parameters"].update(unread={"default": 1}))
    problems, notes = rules(target, manifest_of(target))
    assert problems == [] and len(notes) == 1  # three modes share the graph
    (target / "idler.graph.json").write_text("{ not json")
    problems, notes = rules(target, manifest_of(target))
    assert problems == [] and len(notes) == 1 and "could not be read" in notes[0]


def test_a_wrapper_is_never_transpiled():
    manifest = manifest_of(WRAPPER)
    with pytest.raises(GraphError, match="wrapper"):
        transpile_graph(WRAPPER / "block.graph.json", manifest)
    with pytest.raises(GraphError, match="wrapper"):
        graph_script_path(WRAPPER / "block.graph.json", manifest)
    plan = wrapper_for(WRAPPER / "block.graph.json", manifest)
    assert plan.source == "block.py" and plan.language == "cadquery"
    assert wrapper_for(FIXTURES / "graph-twin" / "block.graph.json",
                       manifest_of(FIXTURES / "graph-twin")) is None


def test_a_native_1_2_graph_transpiles_through_the_core(tmp_path):
    """A native graph may adopt the 1.2 fields; the engine still writes its program."""
    target = tmp_path / "graph-twin"
    shutil.copytree(FIXTURES / "graph-twin", target)
    manifest = manifest_of(target)
    before = transpile_graph(target / "block.graph.json", manifest)

    def upgrade(doc):
        doc.update(version="1.2.0", kernel="solid", licence={"spdx": "CC0-1.0"},
                   declarations={"parameters": copy.deepcopy(manifest["parameters"])})

    rewrite(target / "block.graph.json", upgrade)
    after = transpile_graph(target / "block.graph.json", manifest)
    assert after == before
    assert Path(graph_script_path(target / "block.graph.json", manifest)).read_text() == after


# ── Renders ────────────────────────────────────────────────────────────────────


def _parity(cartridge: Path, tmp_path: Path):
    from y4d_spec.geometry import check_geometry
    from y4d_spec.parity import parity_checks

    renders = check_geometry(cartridge, manifest_of(cartridge), stl_dir=tmp_path)
    return renders, parity_checks(renders, doc=manifest_of(cartridge))


@pytest.mark.geometry
def test_cadquery_wrapper_renders_byte_identically_at_defaults_and_presets(tmp_path):
    renders, pairs = _parity(WRAPPER, tmp_path)
    assert all(r.ok for r in renders), [r.problems for r in renders if not r.ok]
    wrapped = [r for r in renders if r.engine == "graph"]
    assert wrapped and all(r.wraps == "cadquery" for r in wrapped)
    assert len(pairs) == len(wrapped)
    assert all(p.ok and p.report.get("wrapper_identity") for p in pairs), \
        [p.reason for p in pairs]
    assert {p.preset for p in pairs} == {None, "big_block", "chamfered_hollow", "thick_plate"}


@pytest.mark.geometry
def test_pass_through_reaches_the_script_with_its_type(tmp_path):
    """The select (a string) and the checkbox (a boolean) change the solid: if the
    pass-through had coerced them, the preset would render the defaults' volume."""
    from y4d_spec.geometry import render_part_graph

    manifest = manifest_of(WRAPPER)
    plain = render_part_graph(WRAPPER, "block.graph.json", "block", "block",
                              manifest=manifest, params={"block_size": 16.0})
    shaped = render_part_graph(WRAPPER, "block.graph.json", "block", "block",
                               manifest=manifest,
                               params={"block_size": 16.0, "finish": "chamfer",
                                       "hollow": True})
    assert plain.ok and shaped.ok
    assert shaped.volume < plain.volume * 0.6


@pytest.mark.geometry
def test_a_wrapper_refuses_a_part_it_does_not_output():
    from y4d_spec.geometry import render_part_graph

    check = render_part_graph(WRAPPER, "plate.graph.json", "plate", "block",
                              manifest=manifest_of(WRAPPER))
    assert not check.ok and "Unknown target_part" in check.problems[0]


@pytest.mark.geometry
def test_openscad_wrapper_renders_byte_identically(tmp_path):
    from y4d_spec.openscad import openscad_binary

    if openscad_binary() is None:
        pytest.skip("no OpenSCAD binary on this machine")
    renders, pairs = _parity(WRAPPER_SCAD, tmp_path)
    assert all(r.ok for r in renders), [r.problems for r in renders if not r.ok]
    assert pairs and all(p.pairing == ("openscad", "graph") for p in pairs)
    assert all(p.ok and p.report.get("wrapper_identity") for p in pairs)


def test_wrapper_identity_fails_on_any_byte(tmp_path):
    from types import SimpleNamespace

    from y4d_spec.parity import parity_checks

    a, b = tmp_path / "a.stl", tmp_path / "b.stl"
    a.write_bytes(b"solid x\nendsolid x\n")
    b.write_bytes(b"solid x\nendsolid y\n")
    script = SimpleNamespace(mode="m", part="p", preset=None, ok=True, engine="cadquery",
                             stl_path=str(a), wraps=None)
    graph = SimpleNamespace(mode="m", part="p", preset=None, ok=True, engine="graph",
                            stl_path=str(b), wraps="cadquery")
    # An exemption in the manifest does not reach a wrapper pair.
    exempt = {"verification": {"stages": {"geometry": {"checks": {"parity": {
        "enabled": False, "reason": "kernel idioms differ"}}}}}}
    [check] = parity_checks([script, graph], doc=exempt)
    assert not check.ok and not check.exempt
    assert "wrapper differs from its script" in check.reason
    assert hashlib.sha256(a.read_bytes()).hexdigest()[:12] in check.reason


def test_a_part_picker_parameter_and_foreign_bindings_pass_the_wrapper_rules(scratch):
    """The two shapes the P1 pre-check found in the commons, end to end through the
    no-render rules: `target_part` declared as a manifest parameter (and set by a
    preset), and a parameter bound into another graph of the cartridge."""
    picker = {"id": "target_part", "type": "select", "default": "block",
              "label": {"en": "Part"},
              "options": [{"value": "block", "label": {"en": "Block"}}]}

    def manifest(m):
        m["parameters"].append(picker)
        m["parameters"][0]["binding"] = "native_block.w"

    def graph(doc):
        doc["declarations"]["parameters"].append(picker)
        for p in doc["declarations"]["parameters"]:
            if p["id"] == "block_size":
                p["binding"] = "native_block.w"

    rewrite(scratch / "project.json", manifest)
    rewrite(scratch / "block.graph.json", graph)
    rewrite(scratch / "plate.graph.json", graph)
    assert graph_core_rules(scratch, manifest_of(scratch)) == ([], [])
