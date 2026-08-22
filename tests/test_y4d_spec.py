"""Tests for the y4d-spec cartridge conformance runner.

Built on REAL cartridges copied from the yantra4d commons (tests/fixtures/y4d):
`sew-on-snap` (3 modes, 3 parts, one assembly mode) and `thimble` (2 modes, 2 parts).
Both are small, both are CadQuery, both are correct today — so any rule that flags
them is wrong, which is the property most of these tests assert.

Geometry tests are marked `geometry` and skip unless cadquery + trimesh import.
"""

import copy
import json
from pathlib import Path

import pytest

from y4d_spec import check_cartridge, check_manifest, rules, structure

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


def test_cli_rules_explains_itself(capsys):
    from y4d_spec.cli import main

    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "dispatch_rules" in out and "vendor_rules" in out


# ── geometry (skips without the extra) ───────────────────────────────────────
geometry_required = pytest.mark.skipif(
    not __import__("y4d_spec.geometry", fromlist=["geometry_available"]).geometry_available(),
    reason="needs the [geometry] extra (cadquery + trimesh)",
)


@pytest.mark.geometry
@geometry_required
@pytest.mark.parametrize("cartridge", REAL_CARTRIDGES, ids=lambda p: p.name)
def test_real_cartridge_renders_every_part(cartridge):
    result = check_cartridge(cartridge, render=True)
    assert result.rendered
    assert result.ok, [c.summary for c in result.renders if not c.ok]
    assert len(result.renders) == len(rules.render_targets(_manifest(cartridge)))
    for check in result.renders:
        assert check.watertight
        assert check.volume > 0


@pytest.mark.geometry
@geometry_required
def test_assembly_volume_is_the_sum_of_its_parts():
    """sew-on-snap's 'set' mode is the stud and socket side by side. If the volumes
    do not add up, target_part is not really selecting different bodies."""
    result = check_cartridge(SEW_ON_SNAP, render=True)
    by_part = {c.part: c.volume for c in result.renders}
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
