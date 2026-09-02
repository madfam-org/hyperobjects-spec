"""Tests for the y4d-spec cartridge conformance runner.

Built on REAL cartridges copied from the yantra4d commons (tests/fixtures/y4d):
`sew-on-snap` (3 modes, 3 parts, one assembly mode) and `thimble` (2 modes, 2 parts).
Both are small, both are CadQuery, both are correct today — so any rule that flags
them is wrong, which is the property most of these tests assert.

Geometry tests are marked `geometry` and skip unless cadquery + trimesh import.
"""

import copy
import json
import sys
import types
import warnings
from pathlib import Path

import pytest

from y4d_spec import check_cartridge, check_manifest, printability, rules, structure

FIXTURES = Path(__file__).parent / "fixtures" / "y4d"
SEW_ON_SNAP = FIXTURES / "sew-on-snap"
THIMBLE = FIXTURES / "thimble"

REAL_CARTRIDGES = [SEW_ON_SNAP, THIMBLE]


def _manifest(cartridge: Path) -> dict:
    return json.loads((cartridge / "project.json").read_text(encoding="utf-8"))


# ── the real cartridges conform ──────────────────────────────────────────────
@pytest.mark.parametrize("cartridge", REAL_CARTRIDGES, ids=lambda p: p.name)
def test_real_cartridge_conforms(cartridge):
    result = check_cartridge(cartridge)
    assert result.ok, f"{cartridge.name}: {result.problems}"
    assert result.slug == cartridge.name
    assert result.rendered is False  # geometry is opt-in


@pytest.mark.parametrize("cartridge", REAL_CARTRIDGES, ids=lambda p: p.name)
def test_real_cartridge_manifest_alone_conforms(cartridge):
    """check_manifest is the path-independent half — usable on a diff, with no repo."""
    assert check_manifest(_manifest(cartridge)).ok


def test_result_is_falsey_on_problems():
    result = check_cartridge(FIXTURES)  # a directory with no project.json
    assert not result
    assert any("no project.json" in p for p in result.problems)


def test_missing_directory_is_a_problem_not_a_crash():
    result = check_cartridge(FIXTURES / "does-not-exist")
    assert not result.ok
    assert any("not a directory" in p for p in result.problems)


# ── project-block strictness (apps/api/manifest.py) ──────────────────────────
@pytest.mark.parametrize(
    "field,value,expect",
    [
        ("thumbnail", None, "thumbnail"),
        ("tags", "not-a-list", "tags"),
        ("difficulty", "expert", "difficulty"),
    ],
)
def test_project_block_strictness(field, value, expect):
    doc = _manifest(SEW_ON_SNAP)
    if value is None:
        doc["project"].pop(field)
    else:
        doc["project"][field] = value
    problems = rules.manifest_structural_rules(doc)
    assert any(expect in p for p in problems), problems


def test_strictness_reports_what_the_platform_only_warns_about():
    """In-repo these default silently at MANIFEST_STRICTNESS=warn. A spec runner has
    no app to keep serving, so it reports them."""
    doc = _manifest(SEW_ON_SNAP)
    doc["project"].pop("thumbnail")
    doc["project"]["difficulty"] = "impossible"
    assert len(rules.manifest_structural_rules(doc)) == 2


# ── dispatch: the per-part alignment rule ────────────────────────────────────
def test_single_part_cq_mode_must_match_its_part_id():
    """The rule that catches the real hook-and-eye defect: main.py branches on
    target_part=='hook' while the manifest maps mode 'hook' to part 'hook_plate',
    so the platform renders the fallback body."""
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][1]["parts"] = ["socket"]  # mode 'stud' now claims to render socket
    problems = rules.dispatch_rules(doc)
    assert any("single-part CadQuery mode" in p and "'stud'" in p for p in problems), problems


def test_multi_part_mode_is_exempt_from_dispatch_alignment():
    """A multi-part mode renders an assembly via the script's default branch — its id
    is free. sew-on-snap's 'set' mode is single-part-and-aligned; make it multi."""
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["parts"] = ["stud", "socket"]
    assert not any("single-part CadQuery mode" in p for p in rules.dispatch_rules(doc))


def test_openscad_mode_is_exempt_from_target_part_alignment():
    """OpenSCAD dispatches by the render_mode integer, not target_part — misaligned
    ids there are labels, not bugs (projects/custom-msh)."""
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][1]["parts"] = ["socket"]
    for mode in doc["modes"]:
        mode["scad_file"] = "part.scad"
        mode.pop("cq_file", None)
    assert not any("single-part CadQuery mode" in p for p in rules.dispatch_rules(doc))


def test_mode_referencing_unknown_part_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["parts"] = ["ghost"]
    problems = rules.dispatch_rules(doc)
    assert any("unknown part 'ghost'" in p for p in problems), problems


def test_unreachable_part_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parts"].append({"id": "orphan", "label": {"en": "O", "es": "O"}})
    problems = rules.dispatch_rules(doc)
    assert any("orphan" in p and "never be rendered" in p for p in problems), problems


def test_duplicate_mode_id_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][1]["id"] = doc["modes"][0]["id"]
    assert any("duplicate mode id" in p for p in rules.dispatch_rules(doc))


def test_duplicate_parameter_id_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parameters"].append(copy.deepcopy(doc["parameters"][0]))
    assert any("declared more than once" in p for p in rules.dispatch_rules(doc))


def test_parameter_scoped_to_unknown_mode_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parameters"][0]["modes"] = ["no-such-mode"]
    problems = rules.dispatch_rules(doc)
    assert any("unknown mode 'no-such-mode'" in p for p in problems), problems


def test_slug_only_mode_is_reported_as_unrenderable():
    """The schema allows `slug`, but the platform's accessors read mode['id']
    (projects/rugged-box is the one cartridge that does this)."""
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["slug"] = doc["modes"][0].pop("id")
    problems = rules.dispatch_rules(doc)
    assert any("identified by 'slug'" in p for p in problems), problems


def test_parameter_colliding_with_a_kernel_name_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parameters"][0]["id"] = "cq"
    assert any("collides with a name" in p for p in rules.dispatch_rules(doc))


def test_target_part_parameter_is_not_a_collision():
    """Declaring target_part as a select of the part ids is the canonical way to expose
    part selection (projects/body-form) — it must not be flagged."""
    doc = _manifest(SEW_ON_SNAP)
    doc["parameters"].append(
        {
            "id": "target_part",
            "type": "select",
            "default": "set",
            "label": {"en": "Part", "es": "Pieza"},
            "options": [{"value": p["id"], "label": p["label"]} for p in doc["parts"]],
        }
    )
    problems = rules.dispatch_rules(doc)
    assert not any("collides" in p for p in problems), problems
    assert not any("target_part" in p for p in problems), problems


def test_target_part_option_naming_no_part_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parameters"].append(
        {
            "id": "target_part",
            "type": "select",
            "default": "set",
            "label": {"en": "Part", "es": "Pieza"},
            "options": [{"value": "ghost", "label": {"en": "G", "es": "G"}}],
        }
    )
    assert any("names no declared part" in p for p in rules.dispatch_rules(doc))


# ── hyperobject block (compliance_audit.py) ──────────────────────────────────
def test_hyperobject_missing_top_level_block_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc.pop("hyperobject")
    problems = rules.hyperobject_rules(doc)
    assert any("no top-level 'hyperobject' block" in p for p in problems), problems


@pytest.mark.parametrize("tag", ["hyperobject", "commons"])
def test_hyperobject_missing_required_tag_fails(tag):
    doc = _manifest(SEW_ON_SNAP)
    doc["project"]["tags"] = [t for t in doc["project"]["tags"] if t != tag]
    doc["tags"] = [t for t in doc.get("tags", []) if t != tag]
    assert any(f"'{tag}' tag" in p for p in rules.hyperobject_rules(doc))


def test_cdg_interface_referencing_unknown_parameter_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["hyperobject"]["cdg_interfaces"][0]["parameters"] = ["not_a_param"]
    problems = rules.hyperobject_rules(doc)
    assert any("unknown parameter 'not_a_param'" in p for p in problems), problems


def test_missing_export_formats_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc.pop("export_formats")
    assert any("export_formats" in p for p in rules.hyperobject_rules(doc))


def test_non_hyperobject_still_needs_export_formats():
    doc = {"project": {"name": "x", "slug": "x", "version": "1.0.0"}}
    assert any("export_formats" in p for p in rules.hyperobject_rules(doc))


# ── i18n ─────────────────────────────────────────────────────────────────────
def test_missing_spanish_label_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["label"] = {"en": "Only English"}
    problems = rules.i18n_rules(doc)
    assert any("missing 'es' translation" in p for p in problems), problems


def test_bare_string_label_counts_as_english_only():
    doc = _manifest(SEW_ON_SNAP)
    doc["parts"][0]["label"] = "Snap Set"
    assert any("missing 'es'" in p for p in rules.i18n_rules(doc))


def test_name_is_accepted_as_a_display_string():
    """projects/body-form names its parts with `name`, not `label`; the schema does
    not constrain parts items at all, so both are valid."""
    doc = _manifest(SEW_ON_SNAP)
    for part in doc["parts"]:
        part["name"] = part.pop("label")
    assert not any("missing a display string" in p for p in rules.i18n_rules(doc))


def test_missing_display_string_entirely_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["parts"][0].pop("label")
    assert any("missing a display string" in p for p in rules.i18n_rules(doc))


# ── license ──────────────────────────────────────────────────────────────────
def test_hyperobject_without_commons_license_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["hyperobject"].pop("commons_license")
    assert any("commons_license" in p for p in rules.license_rules(doc))


def test_attribution_without_a_source_fails():
    doc = _manifest(SEW_ON_SNAP)
    doc["project"]["attribution"] = {"note": "somewhere"}
    assert any("names no source" in p for p in rules.license_rules(doc))


def test_attribution_with_a_source_passes():
    doc = _manifest(SEW_ON_SNAP)
    doc["project"]["attribution"] = {"source": "upstream/thing"}
    assert not any("attribution" in p for p in rules.license_rules(doc))


# ── on-disk structure ────────────────────────────────────────────────────────
def test_mode_naming_a_missing_file_fails(tmp_path):
    cartridge = tmp_path / "c"
    cartridge.mkdir()
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["scad_file"] = "nope.py"
    problems = structure.mode_source_rules(cartridge, doc)
    assert any("nope.py" in p and "does not exist" in p for p in problems), problems


def test_vendor_directory_fails(tmp_path):
    (tmp_path / "vendor").mkdir()
    assert structure.vendor_rules(tmp_path)


def test_no_vendor_directory_passes(tmp_path):
    assert structure.vendor_rules(tmp_path) == []


def test_absolute_scad_include_is_a_problem(tmp_path):
    (tmp_path / "a.scad").write_text("include </etc/evil.scad>\n")
    problems, notes = structure.source_path_rules(tmp_path)
    assert any("absolute path" in p for p in problems), problems
    assert notes == []


def test_shared_libs_include_is_a_note_not_a_failure(tmp_path):
    """~40 yantra4d cartridges include <../../libs/BOSL2/std.scad> and the platform's
    own lane exempts it. Failing them would make this runner stricter than the
    platform it mirrors."""
    cart = tmp_path / "projects" / "c"
    cart.mkdir(parents=True)
    (tmp_path / "libs").mkdir()
    (cart / "a.scad").write_text("include <../../libs/BOSL2/std.scad>\n")
    problems, notes = structure.source_path_rules(cart)
    assert problems == []
    assert any("shared library tree" in n for n in notes), notes


def test_escaping_include_outside_libs_is_a_problem(tmp_path):
    cart = tmp_path / "projects" / "c"
    cart.mkdir(parents=True)
    (cart / "a.scad").write_text("use <../other-cartridge/part.scad>\n")
    problems, _ = structure.source_path_rules(cart)
    assert any("escapes the cartridge" in p for p in problems), problems


def test_html_license_file_is_a_conflict(tmp_path):
    (tmp_path / "LICENSE").write_text("<!DOCTYPE html><html>404 Not Found</html>")
    problems = structure.shipped_license_rules(
        tmp_path, {"hyperobject": {"commons_license": "CERN-OHL-W-2.0"}}
    )
    assert any("is HTML" in p for p in problems), problems


def test_mismatched_license_file_is_a_conflict(tmp_path):
    (tmp_path / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\nVersion 3\n")
    problems = structure.shipped_license_rules(
        tmp_path, {"hyperobject": {"commons_license": "CERN-OHL-W-2.0"}}
    )
    assert any("declared-vs-shipped" in p for p in problems), problems


def test_matching_license_file_passes(tmp_path):
    (tmp_path / "LICENSE").write_text("CERN Open Hardware Licence Version 2 - Weakly Reciprocal\n")
    assert (
        structure.shipped_license_rules(
            tmp_path, {"hyperobject": {"commons_license": "CERN-OHL-W-2.0"}}
        )
        == []
    )


def test_absent_license_file_is_silent(tmp_path):
    """Only submodule-published cartridges need their own LICENSE, and this package
    cannot know which those are — so absence is silent, conflict is not."""
    assert (
        structure.shipped_license_rules(
            tmp_path, {"hyperobject": {"commons_license": "CERN-OHL-W-2.0"}}
        )
        == []
    )


# ── the render work list ─────────────────────────────────────────────────────
def test_render_targets_is_every_mode_part_pair():
    targets = rules.render_targets(_manifest(SEW_ON_SNAP))
    assert targets == [("set", "set"), ("stud", "stud"), ("socket", "socket")]


def test_render_targets_expands_a_multi_part_mode():
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["parts"] = ["stud", "socket"]
    targets = rules.render_targets(doc)
    assert ("set", "stud") in targets and ("set", "socket") in targets


# ── the preset work list ─────────────────────────────────────────────────────
def test_preset_targets_covers_each_presets_mode_parts():
    """sew-on-snap ships two presets, both scoped to the single-part 'set' mode."""
    targets = rules.preset_targets(_manifest(SEW_ON_SNAP))
    assert [(pid, mid, part) for pid, mid, part, _ in targets] == [
        ("bodysuit_placket", "set", "set"),
        ("varsity_placket", "set", "set"),
    ]
    assert all(v["snap_dia"] for _, _, _, v in targets)


def test_preset_targets_expands_a_multi_part_mode():
    doc = _manifest(SEW_ON_SNAP)
    doc["modes"][0]["parts"] = ["stud", "socket"]
    parts = {part for _, _, part, _ in rules.preset_targets(doc)}
    assert parts == {"stud", "socket"}


def test_preset_without_a_mode_is_scoped_from_parameter_visibility():
    """164 of the commons' 1219 presets declare no `mode` — including every preset of
    extrusion-hyperobject, the cartridge whose shipped preset proved this bug class.
    Skipping them would skip the case this exists for, so they are scoped from the
    manifest: the modes in which all of the preset's parameters are visible."""
    doc = _manifest(SEW_ON_SNAP)
    for preset in doc["presets"]:
        preset.pop("mode")
    # sew-on-snap's parameters are visible everywhere, so an unscoped preset reaches
    # every mode.
    modes = {mid for _, mid, _, _ in rules.preset_targets(doc)}
    assert modes == {"set", "stud", "socket"}


def test_unscoped_preset_is_narrowed_by_a_mode_scoped_parameter():
    """extrusion-hyperobject's `curtain_wall` sets wall_thickness, which is
    visible_in_modes ['frame', 'module_track'] — so it is not a 'rail' preset, and
    rendering it as one would invent a combination the UI cannot produce."""
    doc = _manifest(SEW_ON_SNAP)
    for preset in doc["presets"]:
        preset.pop("mode")
    for param in doc["parameters"]:
        if param["id"] == "snap_dia":
            param["visible_in_modes"] = ["stud"]
    modes = {mid for pid, mid, _, _ in rules.preset_targets(doc)}
    assert modes == {"stud"}


def test_unscoped_preset_with_no_common_mode_is_skipped():
    """An empty intersection means the preset belongs nowhere the UI can reach — it is
    skipped rather than forced into a mode it does not belong to."""
    doc = _manifest(SEW_ON_SNAP)
    for preset in doc["presets"]:
        preset.pop("mode")
    scopes = {"snap_dia": ["stud"], "disc_t": ["socket"]}
    for param in doc["parameters"]:
        if param["id"] in scopes:
            param["visible_in_modes"] = scopes[param["id"]]
    assert rules.preset_targets(doc) == []


def test_preset_naming_an_unknown_mode_is_skipped():
    doc = _manifest(SEW_ON_SNAP)
    doc["presets"][0]["mode"] = "no-such-mode"
    assert [pid for pid, _, _, _ in rules.preset_targets(doc)] == ["varsity_placket"]


def test_preset_that_only_restates_defaults_changes_nothing():
    """thimble ships a preset literally called 'default' that restates
    finger_girth=56.0 — the UI's reset button. It SHOULD render identically."""
    doc = _manifest(THIMBLE)
    defaults = rules.parameter_defaults(doc)
    values = doc["presets"][0]["values"]
    assert values == {"finger_girth": 56.0}
    assert not rules.preset_changes_anything(values, defaults)


def test_preset_that_differs_from_defaults_changes_something():
    doc = _manifest(THIMBLE)
    defaults = rules.parameter_defaults(doc)
    assert rules.preset_changes_anything({"finger_girth": 72.0}, defaults)


def test_preset_value_with_no_declared_default_counts_as_a_change():
    """The script may supply that default via the PARAM idiom, which this function
    cannot see — so it asks the geometry rather than staying silent."""
    assert rules.preset_changes_anything({"undeclared": 3}, {"finger_girth": 56.0})


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_check_passes_on_real_cartridges(capsys):
    from y4d_spec.cli import main

    rc = main(["check", str(SEW_ON_SNAP), str(THIMBLE)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cartridges=2 failures=0" in out
    # Read-proof: a run that skipped geometry must never read like one that passed it.
    assert "geometry=NOT verified" in out


def test_cli_check_fails_on_a_broken_cartridge(capsys, tmp_path):
    from y4d_spec.cli import main

    cart = tmp_path / "broken"
    cart.mkdir()
    doc = _manifest(SEW_ON_SNAP)
    doc["project"].pop("thumbnail")
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.py").write_text("x = 1\n")
    rc = main(["check", str(cart)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_summary_reports_the_preset_count(capsys):
    """Read-proof: a run that skipped the preset lane must never read like one that
    passed it, so the count is on the summary line whether or not presets ran."""
    from y4d_spec.cli import main

    assert main(["check", str(SEW_ON_SNAP)]) == 0
    out = capsys.readouterr().out
    assert "renders=0 presets=0" in out


def test_cli_rules_explains_itself(capsys):
    from y4d_spec.cli import main

    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "dispatch_rules" in out and "vendor_rules" in out
    assert "thin_wall_note" in out and "preset" in out


# ── geometry (skips without the extra) ───────────────────────────────────────
geometry_required = pytest.mark.skipif(
    not __import__("y4d_spec.geometry", fromlist=["geometry_available"]).geometry_available(),
    reason="needs the [geometry] extra (cadquery + trimesh)",
)


@pytest.mark.geometry
@geometry_required
@pytest.mark.parametrize("cartridge", REAL_CARTRIDGES, ids=lambda p: p.name)
def test_real_cartridge_renders_every_part(cartridge):
    doc = _manifest(cartridge)
    result = check_cartridge(cartridge, render=True, printability=False)
    assert result.rendered
    assert result.ok, [c.summary for c in result.renders if not c.ok]
    assert len(result.renders) == len(rules.render_targets(doc)) + len(
        rules.preset_targets(doc)
    )
    for check in result.renders:
        assert check.watertight
        assert check.volume > 0


@pytest.mark.geometry
@geometry_required
@pytest.mark.parametrize("cartridge", REAL_CARTRIDGES, ids=lambda p: p.name)
def test_no_presets_renders_defaults_only(cartridge):
    """--no-presets is strictly weaker and must SAY so by rendering fewer targets —
    a flag that silently changes nothing is worse than no flag."""
    result = check_cartridge(cartridge, render=True, presets=False, printability=False)
    assert result.ok, [c.summary for c in result.renders if not c.ok]
    assert result.preset_renders == []
    assert len(result.renders) == len(rules.render_targets(_manifest(cartridge)))


@pytest.mark.geometry
@geometry_required
def test_assembly_volume_is_the_sum_of_its_parts():
    """sew-on-snap's 'set' mode is the stud and socket side by side. If the volumes
    do not add up, target_part is not really selecting different bodies."""
    result = check_cartridge(SEW_ON_SNAP, render=True, printability=False)
    by_part = {c.part: c.volume for c in result.renders if c.preset is None}
    assert by_part["set"] == pytest.approx(by_part["stud"] + by_part["socket"], rel=1e-6)


@pytest.mark.geometry
@geometry_required
def test_dead_dispatch_is_caught(tmp_path):
    """Cut the socket branch out of the cartridge: 'socket' now falls through to the
    else-branch set assembly, so two distinct parts (socket, set) render the fallback
    body — the distinct-modes check must say so. (One part matching the fallback is
    legitimate — sew-on-snap's own 'set' IS the else-branch; two is a dead dispatch.)"""
    cart = tmp_path / "dead-dispatch"
    cart.mkdir()
    (cart / "project.json").write_text((SEW_ON_SNAP / "project.json").read_text())
    src = (SEW_ON_SNAP / "main.py").read_text()
    broken = src.replace('elif target_part == "socket":', 'elif target_part == "NEVER":')
    assert broken != src, "fixture changed shape — update this test"
    (cart / "main.py").write_text(broken)

    result = check_cartridge(cart, render=True)
    assert not result.ok
    assert any("not distinguishing these parts" in p for p in result.problems), result.problems


@pytest.mark.geometry
@geometry_required
def test_open_shell_is_not_watertight(tmp_path):
    cart = tmp_path / "holed"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    doc["modes"] = [
        {
            "id": "shell",
            "label": {"en": "Shell", "es": "Cascaron"},
            "scad_file": "main.py",
            "cq_file": "main.py",
            "parts": ["shell"],
            "estimate": {"base_time": 1},
        }
    ]
    doc["parts"] = [{"id": "shell", "label": {"en": "Shell", "es": "Cascaron"}}]
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.py").write_text(
        "import cadquery as cq\n"
        "box = cq.Workplane('XY').box(10, 10, 10)\n"
        "# drop the top face: a real open shell that exports fine but encloses nothing\n"
        "result = cq.Workplane(obj=cq.Shell.makeShell(\n"
        "    [f for f in box.val().Faces() if f.Center().z < 4.9]))\n"
    )
    result = check_cartridge(cart, render=True)
    assert not result.ok
    assert any("not watertight" in p for p in result.problems), result.problems


@pytest.mark.geometry
@geometry_required
def test_cartridge_that_assigns_no_result_is_caught(tmp_path):
    cart = tmp_path / "no-result"
    cart.mkdir()
    (cart / "project.json").write_text((THIMBLE / "project.json").read_text())
    (cart / "main.py").write_text("x = 1 + 1\n")
    result = check_cartridge(cart, render=True)
    assert not result.ok
    assert any("no CadQuery Workplane" in p for p in result.problems), result.problems


@pytest.mark.geometry
@geometry_required
def test_render_runs_in_the_shared_sandbox(tmp_path):
    """The render path must go through commons_sandbox — a cartridge that imports os
    is refused, exactly as it would be on the platform."""
    cart = tmp_path / "escapes"
    cart.mkdir()
    (cart / "project.json").write_text((THIMBLE / "project.json").read_text())
    (cart / "main.py").write_text("import os\nresult = os.getcwd()\n")
    result = check_cartridge(cart, render=True)
    assert not result.ok
    assert any("ImportError" in p or "not allowed" in p for p in result.problems), result.problems


# ── the preset matrix (geometry) ─────────────────────────────────────────────
@pytest.mark.geometry
@geometry_required
def test_real_cartridge_presets_render(tmp_path):
    """sew-on-snap's two presets are real snap sizes; both must render, and both must
    differ from the default-params body (9mm and 17mm are not the 12mm default)."""
    result = check_cartridge(SEW_ON_SNAP, render=True, printability=False)
    presets = {c.preset: c for c in result.preset_renders}
    assert set(presets) == {"bodysuit_placket", "varsity_placket"}
    baseline = next(c for c in result.renders if c.preset is None and c.part == "set")
    for check in presets.values():
        assert check.ok, check.summary
        assert check.volume != pytest.approx(baseline.volume, abs=1e-6)
    assert result.notes == []


@pytest.mark.geometry
@geometry_required
def test_a_preset_that_crashes_is_a_failure(tmp_path):
    """The proven bug class: a SHIPPED preset of extrusion-hyperobject crashed the CAD
    kernel at degradation_state=5 while the default-params render stayed green. Here
    the cartridge raises only above a threshold the default never reaches, so the
    defaults pass and only the preset render can catch it."""
    cart = tmp_path / "crashing-preset"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    doc["presets"] = [
        {
            "id": "wide_finger",
            "mode": "thimble",
            "label": {"en": "Wide", "es": "Ancho"},
            "values": {"finger_girth": 78.0},
        }
    ]
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.py").write_text(
        "import cadquery as cq\n"
        "try:\n"
        "    girth = finger_girth\n"
        "except NameError:\n"
        "    girth = 56.0\n"
        "try:\n"
        "    which = target_part\n"
        "except NameError:\n"
        "    which = 'thimble'\n"
        "# Crashes only ABOVE a girth the defaults never reach — so only the preset\n"
        "# lane can see it, which is the whole point of this test.\n"
        "if girth > 70:\n"
        "    raise ValueError('OCCT: BRep_API command not done')\n"
        "if which == 'thimble':\n"
        "    result = cq.Workplane('XY').cylinder(20, girth / 6.0)\n"
        "else:\n"
        "    result = cq.Workplane('XY').cylinder(30, girth / 4.0)\n"
    )

    result = check_cartridge(cart, render=True, printability=False)
    assert not result.ok
    # The defaults render is green — only the preset lane sees this.
    assert all(c.ok for c in result.renders if c.preset is None)
    assert any(
        "preset 'wide_finger'" in p and "ValueError" in p for p in result.problems
    ), result.problems


@pytest.mark.geometry
@geometry_required
def test_a_preset_whose_values_never_reach_the_script_is_a_note(tmp_path):
    """A preset that DIFFERS from the manifest defaults but renders identical geometry
    means the parameter never arrived. A note, not a failure — it does not block."""
    cart = tmp_path / "inert-preset"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    doc["presets"] = [
        {
            "id": "wide_finger",
            "mode": "thimble",
            "label": {"en": "Wide", "es": "Ancho"},
            "values": {"finger_girth": 78.0},
        }
    ]
    (cart / "project.json").write_text(json.dumps(doc))
    # Dispatches on target_part (so the parts stay distinct) but ignores every OTHER
    # parameter — so the preset's finger_girth changes nothing.
    (cart / "main.py").write_text(
        "import cadquery as cq\n"
        "try:\n"
        "    which = target_part\n"
        "except NameError:\n"
        "    which = 'thimble'\n"
        "result = cq.Workplane('XY').cylinder(20 if which == 'thimble' else 30, 9)\n"
    )

    result = check_cartridge(cart, render=True, printability=False)
    assert result.ok, result.problems  # a note never blocks
    assert any(
        "identical to the default-params render" in n and "wide_finger" in n
        for n in result.notes
    ), result.notes


@pytest.mark.geometry
@geometry_required
def test_a_preset_that_only_restates_the_defaults_is_silent(tmp_path):
    """thimble's 'default' preset restates finger_girth=56.0 — the UI's reset button.
    It renders identically BY DESIGN, and noting it would be a false positive."""
    result = check_cartridge(THIMBLE, render=True, printability=False)
    assert result.ok, result.problems
    assert [c.preset for c in result.preset_renders] == ["default"]
    assert result.notes == []


@pytest.mark.geometry
@geometry_required
def test_openscad_preset_is_skipped_like_its_mode(tmp_path):
    """OpenSCAD modes are skipped in the defaults pass; their presets must be too —
    this runner has no OpenSCAD kernel and never pretends otherwise."""
    cart = tmp_path / "scad-preset"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    for mode in doc["modes"]:
        mode["scad_file"] = "main.scad"
        mode.pop("cq_file", None)
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.scad").write_text("cube([10,10,10]);\n")

    result = check_cartridge(cart, render=True)
    assert result.ok, result.problems
    assert result.preset_renders == []


# ── printability (notes only, never failures) ────────────────────────────────
@pytest.mark.geometry
@geometry_required
def test_thin_wall_note_fires_on_a_thin_wall(tmp_path):
    """A 0.4mm-walled open-topped box: one nozzle width, half the two-perimeter bar."""
    cart = tmp_path / "thin-wall"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    doc["presets"] = []
    # The stock parameters are mode-scoped to thimble/set; this fixture replaces the
    # modes, so drop them rather than leave dangling scope references.
    doc["parameters"] = []
    doc["hyperobject"]["cdg_interfaces"] = []
    doc["modes"] = [
        {
            "id": "shell",
            "label": {"en": "Shell", "es": "Cascaron"},
            "scad_file": "main.py",
            "cq_file": "main.py",
            "parts": ["shell"],
            "estimate": {"base_time": 1},
        }
    ]
    doc["parts"] = [{"id": "shell", "label": {"en": "Shell", "es": "Cascaron"}}]
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.py").write_text(
        "import cadquery as cq\n"
        "# 0.4mm walls — a single 0.4mm nozzle perimeter, below the two-perimeter bar.\n"
        "result = (cq.Workplane('XY').box(20, 20, 10)\n"
        "          .faces('>Z').shell(-0.4))\n"
    )

    result = check_cartridge(cart, render=True)
    assert result.ok, result.problems  # printability NEVER fails a cartridge
    assert any("thin walls" in n for n in result.notes), result.notes
    # The note must name the measured number, not just the verdict.
    assert any("below 0.8mm" in n and "median local thickness" in n for n in result.notes)


@pytest.mark.geometry
@geometry_required
def test_printability_is_silent_on_sew_on_snap_at_its_defaults():
    """sew-on-snap is a correct, shipped, printed cartridge. A printability rule that
    flags it at its own defaults is not strict — it is wrong (the doctrine rules.py
    records for the killed render_mode rule). Both thresholds were tuned against
    exactly this: thin walls flagged all three parts at the 25th percentile, and
    overhangs flagged them at 32% before bed-contact faces were excluded."""
    result = check_cartridge(SEW_ON_SNAP, render=True)
    assert result.ok, result.problems
    default_notes = [n for n in result.notes if "preset" not in n]
    assert default_notes == [], default_notes


@geometry_required
def test_printability_note_on_a_marginal_preset_does_not_block():
    """The one finding the tuned thresholds keep on sew-on-snap, and it is TRUE: the
    'bodysuit_placket' preset is the 9mm snap with 1.6mm discs, and its sew-hole
    webbing measures ~0.76mm median — genuinely marginal for a 0.4mm nozzle, a few
    hundredths under the bar.

    KNOWN FLAKE, and the docstring used to hide it: this said "a stable 0.76mm median
    (0.74-0.78 across eight sample seeds)", and it is not stable. `thin_wall_note`
    estimates the median from 400 UNSEEDED random surface samples, so on a part sitting
    0.04mm under the threshold the estimate wanders across it: 12 consecutive renders
    here measured 0.75-0.80mm and produced NO note on 3 of them. Until PR #9 the
    geometry lane skipped on the runner and nobody could see it; now that the lane
    actually runs, this assertion fails roughly one run in four.

    Fixing it is a calibration decision and not a test edit — seed the sampler so the
    measurement is reproducible, or move the statistic — and it belongs with whoever
    owns the provisional thresholds (printability.py). Do NOT "fix" it by weakening the
    assertion: the assertion is the doctrine, and the doctrine is right.

    The point of this test is that doctrine, not the number: a true-but-marginal
    measurement is exactly what a NOTE is for. It gets said, it names its number so a
    reader can weigh it against 0.80 themselves, and it does not turn a shipped
    cartridge red."""
    result = check_cartridge(SEW_ON_SNAP, render=True)
    assert result.ok, result.problems
    assert any(
        "thin walls" in n and "bodysuit_placket" in n for n in result.notes
    ), result.notes


@pytest.mark.geometry
@geometry_required
def test_no_printability_silences_the_measurements(tmp_path):
    cart = tmp_path / "thin-wall-off"
    cart.mkdir()
    doc = _manifest(THIMBLE)
    doc["presets"] = []
    # The stock parameters are mode-scoped to thimble/set; this fixture replaces the
    # modes, so drop them rather than leave dangling scope references.
    doc["parameters"] = []
    doc["hyperobject"]["cdg_interfaces"] = []
    doc["modes"] = [
        {
            "id": "shell",
            "label": {"en": "Shell", "es": "Cascaron"},
            "scad_file": "main.py",
            "cq_file": "main.py",
            "parts": ["shell"],
            "estimate": {"base_time": 1},
        }
    ]
    doc["parts"] = [{"id": "shell", "label": {"en": "Shell", "es": "Cascaron"}}]
    (cart / "project.json").write_text(json.dumps(doc))
    (cart / "main.py").write_text(
        "import cadquery as cq\n"
        "result = cq.Workplane('XY').box(20, 20, 10).faces('>Z').shell(-0.4)\n"
    )
    result = check_cartridge(cart, render=True, printability=False)
    assert result.ok
    assert result.notes == []


# ── a missing PACKAGE is not an unmeasurable mesh ────────────────────────────
# These run everywhere, in every install, with nothing skipped: they substitute a
# stand-in `trimesh` (and `numpy`) into sys.modules, so they need neither the
# [geometry] extra nor a CAD kernel to pin what the module does when a package the
# measurement reaches for is absent.


class _StubMesh:
    """The little a printability measurement asks of a mesh before it measures."""

    faces = types.SimpleNamespace(shape=(128,))
    area = 10.0
    face_normals = {"face-index": "normals"}


def _stub_trimesh(thickness):
    return types.SimpleNamespace(
        sample=types.SimpleNamespace(
            sample_surface=lambda mesh, n: ("points", "face-index")
        ),
        proximity=types.SimpleNamespace(thickness=thickness),
    )


def _install_stub_trimesh(monkeypatch, thickness):
    monkeypatch.setattr(printability, "_REPORTED_MISSING", set())
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "trimesh", _stub_trimesh(thickness))


def test_a_missing_package_is_named_rather_than_measured_as_silence(monkeypatch):
    """The bug this pins, and the reason the [geometry] extra now declares rtree.

    trimesh.proximity.thickness at its default method='max_sphere' reaches for `rtree`
    (through mesh.ray -> triangles_tree -> util.bounds_tree). The extra did not declare
    it, and the broad `except Exception` turned the resulting ModuleNotFoundError into
    the same None a featureless mesh returns — so `thin_wall` silently never fired, and
    the two tests that assert it DOES fire were green only where the geometry lane was
    skipped wholesale. A missing package must be distinguishable from a mesh with
    nothing to say."""

    def _missing(**kwargs):
        raise ModuleNotFoundError("No module named 'rtree'", name="rtree")

    _install_stub_trimesh(monkeypatch, _missing)

    with pytest.warns(printability.PrintabilityDependencyWarning) as caught:
        note = printability.thin_wall_note(_StubMesh(), mode="m", part="p")

    assert note is None  # printability still never blocks — it reports and moves on
    message = str(caught[0].message)
    assert "rtree" in message, message
    assert "thin_wall" in message and "SKIPPED" in message, message
    assert "hyperobjects-spec[geometry]" in message, message


def test_the_missing_package_is_named_once_per_process_not_once_per_render(monkeypatch):
    """A cartridge measures every (mode, part, preset). Saying it forty times would
    bury the one line that matters."""

    def _missing(**kwargs):
        raise ModuleNotFoundError("No module named 'rtree'", name="rtree")

    _install_stub_trimesh(monkeypatch, _missing)

    with pytest.warns(printability.PrintabilityDependencyWarning) as caught:
        for part in ("a", "b", "c"):
            assert printability.thin_wall_note(_StubMesh(), mode="m", part=part) is None
    assert len(caught) == 1, [str(w.message) for w in caught]


def test_a_geometric_failure_still_gets_silence(monkeypatch):
    """The swallow stays where it belongs. A ray that lands nowhere, a degenerate
    mesh, an OCCT tantrum — those are unmeasurable PARTS, and an unmeasurable part
    gets silence rather than a guess or a warning nobody can act on."""

    def _degenerate(**kwargs):
        raise ValueError("could not cast rays through a degenerate mesh")

    _install_stub_trimesh(monkeypatch, _degenerate)

    with warnings.catch_warnings():
        warnings.simplefilter("error", printability.PrintabilityDependencyWarning)
        assert printability.thin_wall_note(_StubMesh(), mode="m", part="p") is None


def test_build_volume_note_names_the_measurement():
    """Pure-mesh rules need no cadquery — build the mesh in trimesh directly."""
    trimesh = pytest.importorskip("trimesh")
    big = trimesh.creation.box((300.0, 50.0, 50.0))
    note = printability.build_volume_note(big, mode="m", part="p")
    assert note is not None
    assert note.measured == pytest.approx(300.0)
    assert "300" in note.message and "256mm" in note.message


def test_build_volume_note_is_silent_on_a_part_that_fits():
    trimesh = pytest.importorskip("trimesh")
    small = trimesh.creation.box((30.0, 30.0, 30.0))
    assert printability.build_volume_note(small, mode="m", part="p") is None


def test_overhang_note_fires_on_a_downward_facing_cone():
    """A squat cone pointing DOWN is mostly unsupported overhang."""
    trimesh = pytest.importorskip("trimesh")
    import numpy as np

    cone = trimesh.creation.cone(radius=20.0, height=8.0)
    cone.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    note = printability.overhang_note(cone, mode="m", part="p")
    assert note is not None
    assert note.measured > printability.OVERHANG_AREA_FRACTION
    assert "unsupported downward-facing slope" in note.message


def test_overhang_note_is_silent_on_a_sphere():
    """A sphere is half downward-facing by area, but only the steep band counts as
    unsupported — so the >45° share stays under the bar."""
    trimesh = pytest.importorskip("trimesh")
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=10.0)
    assert printability.overhang_note(sphere, mode="m", part="p") is None


def test_a_flat_bottom_resting_on_the_bed_is_not_an_overhang():
    """The calibration finding that tuned this rule: a plain flat plate is 42%
    downward-facing by area, and every bit of it is the face RESTING ON THE BED, which
    needs no support. Counting it flagged sew-on-snap — a shipped, printed cartridge —
    at 32%. Excluding bed-contact faces takes it to 0%."""
    trimesh = pytest.importorskip("trimesh")
    plate = trimesh.creation.box((20.0, 20.0, 2.0))
    assert printability.overhang_note(plate, mode="m", part="p") is None


def test_printability_notes_name_the_preset_they_came_from():
    trimesh = pytest.importorskip("trimesh")
    big = trimesh.creation.box((300.0, 50.0, 50.0))
    notes = printability.printability_notes(big, mode="rail", part="rail", preset="long")
    assert notes
    assert all("preset 'long'" in n.message for n in notes)
