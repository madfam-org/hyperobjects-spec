"""Tests for the dead-parameter rule (G-DEADPARAM).

A declared parameter that no source reads is a control the UI offers which changes
nothing. OpenSCAD is where this hides best — it accepts an unknown `-D name=value` in
silence — but the rule covers all three source dialects, because the failure is the
same one in each.

The fixture `dead-param` reproduces the shapes found in the real solid commons, and
every parameter in it is named for the cartridge it stands in for:

  ALIVE (must never be flagged)
    base_w         used in both sources of its mode
    lever_length   locking-mechanism-hyperobject — scoped to one mode, used THERE
    drainage_angle custom-msh — allow-listed with a reason
    target_part    injected by the runner, exempt unconditionally

  DEAD (must be flagged)
    phone_angle    portacosas — a declaration line in the .scad and nothing else
    mat_width      framing-hyperobject — declared in the .scad, absent from the .py
    drive_type     scara-robotics — named by no source at all

The other real cartridges the sweep found (`prosthetic-socket`, whose script was
rewritten to read `wall` while the manifest still declares `wall_thickness`) are the
same three shapes and are not duplicated here.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from y4d_spec import check_cartridge, rules, structure

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
DEAD_PARAM = FIXTURES / "dead-param"
SEW_ON_SNAP = FIXTURES / "sew-on-snap"
THIMBLE = FIXTURES / "thimble"
SCAD_BLOCK = FIXTURES / "scad-block"


def _manifest(cartridge: Path) -> dict:
    return json.loads((cartridge / "project.json").read_text(encoding="utf-8"))


def _problem_ids(problems: list[str]) -> set[str]:
    """The parameter ids named by dead-parameter problems, ignoring other rules."""
    return {
        p.split("'")[1]
        for p in problems
        if "never referenced" in p and p.startswith("parameter '")
    }


def _dead(cartridge: Path, doc: dict | None = None) -> set[str]:
    doc = _manifest(cartridge) if doc is None else doc
    return _problem_ids(structure.dead_parameter_rules(cartridge, doc))


# ── the fixture's verdict, end to end ────────────────────────────────────────
def test_the_three_dead_shapes_are_all_reported():
    assert _dead(DEAD_PARAM) == {"phone_angle", "mat_width", "drive_type"}


def test_a_dead_parameter_is_a_conformance_failure_not_a_note():
    """Severity is the whole point of the ruling: a note would let the fleet keep
    shipping sliders that move nothing."""
    result = check_cartridge(DEAD_PARAM)
    assert result.ok is False
    assert _problem_ids(result.problems)
    assert not any("never referenced" in n for n in result.notes)


def test_the_message_names_the_sources_it_looked_in_and_the_way_out():
    (problem,) = [
        p for p in structure.dead_parameter_rules(DEAD_PARAM, _manifest(DEAD_PARAM))
        if "'phone_angle'" in p
    ]
    assert "stand.scad" in problem            # where it looked
    assert "intentionally_unused" in problem  # and how to declare it deliberate
    assert "G-DEADPARAM" in problem


# ── the healthy shapes: a rule that fires on these would be wrong ────────────
@pytest.mark.parametrize("cartridge", [SEW_ON_SNAP, THIMBLE, SCAD_BLOCK], ids=lambda p: p.name)
def test_real_conformant_cartridges_have_no_dead_parameters(cartridge):
    assert _dead(cartridge) == set()


def test_a_parameter_used_in_both_sources_of_its_mode_is_alive():
    assert "base_w" not in _dead(DEAD_PARAM)


def test_a_mode_scoped_parameter_is_judged_only_against_the_modes_that_list_it():
    """locking-mechanism-hyperobject.lever_length. It is `visible_in_modes: ["lever"]`
    and used throughout lever.scad; no source of the `stand` mode mentions it. Judging
    it against every mode would call a correctly scoped parameter dead."""
    assert "lever_length" not in _dead(DEAD_PARAM)


def test_widening_that_scope_to_a_mode_that_does_not_use_it_still_passes():
    """The scope decides WHICH sources must be searched, and one hit is enough — a
    parameter offered in two modes and read by one is wired, not dead."""
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "lever_length":
            p["visible_in_modes"] = ["stand", "lever"]
    assert "lever_length" not in _dead(DEAD_PARAM, doc)


def test_narrowing_that_scope_to_a_mode_that_does_not_use_it_fails():
    """The converse, and the reason scoping is not just a way to be lenient: scoped to
    `stand` alone, lever.scad is no longer searched and nothing reads it."""
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "lever_length":
            p["visible_in_modes"] = ["stand"]
    assert "lever_length" in _dead(DEAD_PARAM, doc)


def test_target_part_is_exempt_because_the_runner_injects_it():
    assert "target_part" not in _dead(DEAD_PARAM)


def test_target_part_stays_exempt_even_when_no_source_mentions_it():
    doc = copy.deepcopy(_manifest(SEW_ON_SNAP))
    doc["parameters"].append(
        {
            "id": "target_part",
            "type": "select",
            "options": [{"value": p["id"], "label": {"en": "x", "es": "x"}}
                        for p in doc["parts"]],
            "label": {"en": "Part", "es": "Pieza"},
        }
    )
    assert "target_part" not in _dead(SEW_ON_SNAP, doc)


# ── the allow-list, and its required reason ──────────────────────────────────
def test_an_allow_listed_parameter_with_a_reason_passes():
    assert "drainage_angle" not in _dead(DEAD_PARAM)


def test_an_allow_list_without_a_reason_is_an_error():
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "drainage_angle":
            p["intentionally_unused"] = {}
    problems = structure.dead_parameter_rules(DEAD_PARAM, doc)
    assert any("without a non-empty 'reason'" in p for p in problems), problems


@pytest.mark.parametrize("reason", ["", "   ", "\n\t "])
def test_an_allow_list_whose_reason_is_blank_is_an_error(reason):
    """A reason that is whitespace is a reason nobody can review — the G38 bar."""
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "drainage_angle":
            p["intentionally_unused"] = {"reason": reason}
    problems = structure.dead_parameter_rules(DEAD_PARAM, doc)
    assert any("without a non-empty 'reason'" in p for p in problems), problems


def test_a_malformed_allow_list_is_reported_as_itself():
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "drainage_angle":
            p["intentionally_unused"] = True
    problems = structure.dead_parameter_rules(DEAD_PARAM, doc)
    assert any("must be an object with a 'reason'" in p for p in problems), problems


def test_a_bad_allow_list_does_not_also_produce_a_dead_parameter_line():
    """Two lines for one fault is noise. The exemption is reported; the parameter is
    not additionally reported as dead."""
    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "phone_angle":
            p["intentionally_unused"] = {}
    assert "phone_angle" not in _dead(DEAD_PARAM, doc)


def test_the_schema_requires_a_reason_on_the_allow_list():
    """Belt and braces: the rule enforces it, and so does the manifest schema, so a
    manifest editor is told before a checker ever runs."""
    from y4d_spec.conformance import check_manifest

    doc = copy.deepcopy(_manifest(DEAD_PARAM))
    for p in doc["parameters"]:
        if p["id"] == "drainage_angle":
            p["intentionally_unused"] = {}
    problems = check_manifest(doc).problems
    assert any("schema" in p and "reason" in p for p in problems), problems


# ── the .scad dialect: declaration line vs use ───────────────────────────────
def test_scad_declaration_line_alone_is_not_a_reference():
    """The `-D` overrides that line. This is the whole OpenSCAD failure mode."""
    assert rules.scad_references("phone_angle = 65;\n", "phone_angle") is False


def test_scad_use_in_a_module_body_is_a_reference():
    text = "base_w = 40;\nmodule m() { cube([base_w, 2, 2]); }\n"
    assert rules.scad_references(text, "base_w") is True


def test_scad_use_on_its_own_declarations_right_hand_side_is_a_reference():
    """`w = w * 2;` reads the injected value before overwriting it."""
    assert rules.scad_references("w = w * 2;\n", "w") is True


def test_scad_reference_in_a_comment_does_not_count():
    """custom-msh's `drainage_angle = 5; // Tilt angle (reserved for future ...)` —
    counting the comment would let every dead slider document itself alive."""
    text = "drainage_angle = 5; // reserved for future drainage_angle work\n"
    assert rules.scad_references(text, "drainage_angle") is False


def test_scad_reference_in_a_block_comment_does_not_count():
    text = "x = 1;\n/* someday we will use x here */\n"
    assert rules.scad_references(text, "x") is False


def test_scad_identifier_is_matched_whole_word_only():
    """`wall` must not be rescued by `wall_thickness` — prosthetic-socket is exactly
    this confusion in the other direction."""
    text = "wall = 4;\nmodule m() { cube([wall_thickness, 2, 2]); }\n"
    assert rules.scad_references(text, "wall") is False


def test_scad_absent_identifier_is_not_a_reference():
    assert rules.scad_references("cube([1,2,3]);\n", "drive_type") is False


# ── the .py/.cq dialect: bare globals, not a PARAM library call ──────────────
def test_script_param_lambda_idiom_is_a_reference():
    """The commons idiom. It is caught because the bare identifier is inside it, not
    because `PARAM` is special — params arrive as bare globals (cq_runner.py:43)."""
    text = "wall = float(PARAM(lambda: wall, 4.0))\n"
    assert rules.script_references(text, "wall") is True


def test_script_bare_global_without_the_param_idiom_is_a_reference():
    assert rules.script_references("result = cq.Workplane().box(w, w, w)\n", "w") is True


def test_script_params_subscript_form_is_a_reference():
    """The minority dialect: the id appears only inside a string literal."""
    assert rules.script_references('h = params["height"]\n', "height") is True
    assert rules.script_references("h = params.get('height', 4)\n", "height") is True


def test_script_reference_in_a_comment_does_not_count():
    assert rules.script_references("# mat_width is not wired yet\n", "mat_width") is False


def test_script_reference_in_a_docstring_does_not_count():
    """Prose is not a reference — the same argument that strips `//` from OpenSCAD."""
    text = '"""This cartridge does not read mat_width yet."""\nresult = 1\n'
    assert rules.script_references(text, "mat_width") is False


def test_script_reference_inside_an_fstring_expression_does_count():
    """`f"{wall}"` reads the value; the literal text around it does not."""
    assert rules.script_references('label = f"w={wall}"\n', "wall") is True
    assert rules.script_references('label = f"wall goes here"\n', "wall") is False


def test_script_identifier_is_matched_whole_word_only():
    text = "wall_thickness = 4.0\nresult = wall_thickness\n"
    assert rules.script_references(text, "wall") is False


def test_an_unparseable_script_falls_back_rather_than_crashing():
    """A syntax error is mode_source_rules' business and a render-time failure. This
    rule degrades to line-wise comment stripping instead of raising."""
    assert rules.script_references("def (:\nwall\n", "wall") is True


# ── the .graph.json dialect: parameters[].binding ────────────────────────────
def _graph_doc(binding) -> dict:
    param = {"id": "plate_radius", "type": "slider", "default": 45.0,
             "label": {"en": "R", "es": "R"}}
    if binding is not None:
        param["binding"] = binding
    return {
        "modes": [{"id": "flange", "scad_file": "flange.graph.json", "parts": ["flange"]}],
        "parts": [{"id": "flange", "label": {"en": "F", "es": "F"}}],
        "parameters": [param],
    }


GRAPH_JSON = json.dumps(
    {
        "version": "1.0.0",
        "nodes": [{"id": "outline", "type": "profile_circle", "params": {"r": 45}}],
        "outputs": {"flange": "outline"},
    }
)


def _graph_dead(tmp_path: Path, binding) -> set[str]:
    (tmp_path / "flange.graph.json").write_text(GRAPH_JSON)
    return _problem_ids(structure.dead_parameter_rules(tmp_path, _graph_doc(binding)))


def test_a_graph_parameter_with_a_binding_is_alive(tmp_path):
    """A graph cartridge binds from the MANIFEST side: `binding: "nodeId.param"`. This
    is how flange-plate and spacer-block are actually wired — neither .graph.json
    contains the string "param" at all."""
    assert _graph_dead(tmp_path, "outline.r") == set()


def test_a_graph_parameter_with_a_list_of_bindings_is_alive(tmp_path):
    """One parameter may drive several node params — edge_chamfer does."""
    assert _graph_dead(tmp_path, ["outline.r", "other.distance"]) == set()


def test_a_graph_parameter_with_no_binding_is_dead(tmp_path):
    """The graph renders its own literal and the control drives nothing."""
    assert _graph_dead(tmp_path, None) == {"plate_radius"}


def test_a_graph_parameter_with_an_empty_binding_is_dead(tmp_path):
    assert _graph_dead(tmp_path, "   ") == {"plate_radius"}
    assert _graph_dead(tmp_path, []) == {"plate_radius"}


# ── libraries: a reference from a file the cartridge SHIPS counts ────────────
def _lib_cartridge(tmp_path: Path, include_line: str) -> dict:
    doc = {
        "modes": [{"id": "m", "scad_file": "main.scad", "parts": ["m"]}],
        "parts": [{"id": "m", "label": {"en": "M", "es": "M"}}],
        "parameters": [
            {"id": "rail_w", "type": "slider", "default": 10.0,
             "label": {"en": "W", "es": "W"}}
        ],
    }
    (tmp_path / "main.scad").write_text(f"{include_line}\nrail_w = 10;\nmake();\n")
    return doc


def test_a_reference_in_an_included_file_the_cartridge_ships_counts(tmp_path):
    """`include <>` is textual inclusion into the same variable scope, so the read in
    the library is reading the very global the `-D` sets. The parameter reaches
    geometry, and this rule's premise is that such a parameter is alive."""
    doc = _lib_cartridge(tmp_path, "include <profiles.scad>")
    (tmp_path / "profiles.scad").write_text("module make() { cube([rail_w, 2, 2]); }\n")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == set()


def test_use_resolves_the_same_way_as_include(tmp_path):
    doc = _lib_cartridge(tmp_path, "use <profiles.scad>")
    (tmp_path / "profiles.scad").write_text("module make() { cube([rail_w, 2, 2]); }\n")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == set()


def test_a_shipped_library_that_does_not_use_it_leaves_it_dead(tmp_path):
    doc = _lib_cartridge(tmp_path, "include <profiles.scad>")
    (tmp_path / "profiles.scad").write_text("module make() { cube([1, 2, 3]); }\n")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == {"rail_w"}


def test_an_unresolvable_library_is_skipped_not_treated_as_a_reference(tmp_path):
    """`include <BOSL2/std.scad>` resolves against a path this package does not have.
    Treating the absent file as a reference would exempt every parameter of all 43
    BOSL2 cartridges and switch the rule off where it is most needed."""
    doc = _lib_cartridge(tmp_path, "include <BOSL2/std.scad>")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == {"rail_w"}


def test_an_escaping_library_include_is_skipped_too(tmp_path):
    doc = _lib_cartridge(tmp_path, "include <../../libs/shared.scad>")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == {"rail_w"}


def test_mutually_including_files_terminate(tmp_path):
    """portacosas both `include`s and `use`s the same file, and a cycle is legal."""
    doc = _lib_cartridge(tmp_path, "include <a.scad>")
    (tmp_path / "a.scad").write_text("include <b.scad>\n")
    (tmp_path / "b.scad").write_text("include <a.scad>\nmodule make(){cube([rail_w,2,2]);}\n")
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == set()


# ── a mode whose sources are missing is not evidence either way ──────────────
def test_a_mode_naming_a_missing_source_does_not_produce_a_dead_parameter(tmp_path):
    """mode_source_rules already fails that cartridge. Reporting the same fault twice,
    as a different fault, helps nobody."""
    doc = {
        "modes": [{"id": "m", "scad_file": "gone.scad", "parts": ["m"]}],
        "parts": [{"id": "m", "label": {"en": "M", "es": "M"}}],
        "parameters": [
            {"id": "w", "type": "slider", "default": 1.0, "label": {"en": "W", "es": "W"}}
        ],
    }
    assert _problem_ids(structure.dead_parameter_rules(tmp_path, doc)) == set()


def test_a_parameter_scoped_to_no_existing_mode_is_not_reported(tmp_path):
    """dispatch_rules already reports a scope naming an unknown mode."""
    doc = _manifest(DEAD_PARAM)
    doc = copy.deepcopy(doc)
    for p in doc["parameters"]:
        if p["id"] == "phone_angle":
            p["visible_in_modes"] = ["no-such-mode"]
    assert "phone_angle" not in _dead(DEAD_PARAM, doc)


def test_a_cartridge_with_no_parameters_is_silent(tmp_path):
    doc = {"modes": [], "parts": [], "parameters": []}
    assert structure.dead_parameter_rules(tmp_path, doc) == []
