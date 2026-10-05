"""Assembly resolution, the mating rule's static checks, the digest and the CLI (ASM-1 §3)."""

import copy
import json
import shutil

import pytest

from assembly_helpers import (
    COMMONS,
    SEMANTIC_MOUNT,
    STANDARD,
    assembly,
    assert_matrix,
    cartridge,
    codes,
    mate,
    resolver,
    standard,
)
from hyperobjects_schemas.generator_output import instance_id, tree_sha256, variables_sha256
from y4d_spec.assembly import (
    ComponentResolver,
    CompositeResolver,
    ExternalResolver,
    ResolvedComponent,
    goc1_variables,
    resolve_interfaces,
    validate_assembly,
)
from y4d_spec.cli import main


def _pair(a_comp, b_comp, a_ref, b_ref, **mate_kw):
    return assembly([a_comp, b_comp], [mate("m1", a_ref, b_ref, **mate_kw)])


@pytest.fixture
def fpv_commons(tmp_path):
    """A commons holding the SEM-1 fixture cartridge (a soft motor mount whose bolt
    pattern frame is `plate_thick + iso_gap` above its base, size chosen by a select)."""
    target = tmp_path / "semantic-motor-mount"
    target.mkdir()
    shutil.copy(SEMANTIC_MOUNT, target / "project.json")
    return tmp_path


# ── step 1: structure ─────────────────────────────────────────────────────────
def test_a_document_that_fails_the_schema_stops_there():
    doc = assembly([standard("a", "elbow-test")], [])
    doc["format"] = "hyperobjects.assemblies"
    del doc["license"]
    report = validate_assembly(doc, resolver())
    assert {c for c, _ in codes(report)} == {"schema"}
    assert not report.components and report.digest is None


def test_a_mate_states_exactly_one_rotation():
    doc = _pair(standard("a", "elbow-test"), standard("b", "elbow-test"), "a.outlet", "b.inlet")
    doc["mates"][0]["angle_deg"] = 0
    assert {c for c, _ in codes(validate_assembly(doc, resolver()))} == {"schema"}


def test_ids_root_and_endpoints():
    doc = assembly(
        [standard("a", "elbow-test"), standard("a", "elbow-test")],
        [mate("m1", "a.outlet", "a.inlet"), mate("m1", "a.outlet", "ghost.inlet")],
        root="nowhere",
    )
    found = set(codes(validate_assembly(doc, resolver())))
    assert {("component-id", "a"), ("mate-id", "m1"), ("root", None),
            ("mate-endpoint", "m1")} <= found


def test_a_product_carries_no_capability_profile():
    doc = assembly([standard("a", "elbow-test")], [], capability_profile={"process": ["fff"]})
    assert {c for c, _ in codes(validate_assembly(doc, resolver()))} == {"schema"}
    doc["kind"] = "producer"
    assert validate_assembly(doc, resolver()).ok


# ── step 2: resolution ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "params, fragment",
    [
        ({"plate_thick": 9}, "above its maximum 8 (out of range is an error, never clamped)"),
        ({"plate_thick": 2.5}, "below its minimum 3"),
        ({"plate_thickness": 5}, "parameter 'plate_thickness' is not declared"),
        ({"slotted": 1}, "is a checkbox; 1 is not a boolean"),
        ({"target_part": "lid"}, "is not one of its options"),
        ({"wall_height": "30"}, "is not a finite number"),
    ],
)
def test_cartridge_parameters_are_checked_never_clamped(params, fragment):
    doc = _pair(cartridge("bracket", **params), standard("motor", "nema-17-48mm-test"),
                "bracket.motor_face", "motor.face")
    report = validate_assembly(doc, resolver())
    assert ("resolve", "bracket") in codes(report)
    assert any(fragment in f.message for f in report.errors), report.errors
    assert report.digest is None and "motor" not in report.placements


def test_standard_part_parameters_are_checked_too():
    doc = assembly([standard("e1", "elbow-test", arm=500)], [])
    report = validate_assembly(doc, resolver())
    assert codes(report) == [("resolve", "e1")]
    assert "above its maximum 200" in report.errors[0].message


@pytest.mark.parametrize(
    "component, fragment",
    [
        (cartridge("x", slug="no-such-cartridge"), "cartridge 'no-such-cartridge' not found"),
        (cartridge("x", mode="spiral"), "has no mode 'spiral' (modes: angle, flat)"),
        (cartridge("x", mode="flat", part="angle_plate"), "does not produce part 'angle_plate'"),
        (standard("x", "no-such-part"), "standard part 'no-such-part' is not in"),
    ],
)
def test_unresolvable_components_are_named(component, fragment):
    report = validate_assembly(assembly([component], []), resolver())
    assert codes(report) == [("resolve", "x")]
    assert fragment in report.errors[0].message


def test_a_missing_resolver_says_which_option_supplies_it():
    doc = assembly([cartridge("b"), standard("m", "nema-17-48mm-test")], [])
    report = validate_assembly(doc, CompositeResolver.for_directories(COMMONS, None))
    assert codes(report) == [("resolve", "m")]
    assert "pass --standard-parts" in report.errors[0].message
    report = validate_assembly(doc, CompositeResolver.for_directories(None, STANDARD))
    assert "pass --commons" in report.errors[0].message


def test_cartridge_identity_is_the_goc1_instance_id():
    """Full injection over the defaults; target_part is an engine-control key and is
    not a variable (GOC-1 §4.3)."""
    report = validate_assembly(assembly([cartridge("b", plate_thick=6.0)], []), resolver())
    variables = {"plate_thick": 6, "slotted": False, "wall_height": 30}
    expected = instance_id(
        cartridge="nema-bracket", mode="flat", part=None,
        tree_sha256=tree_sha256(COMMONS / "nema-bracket"),
        variables_sha256=variables_sha256(variables),
    )
    assert report.components["b"].identity == {"type": "cartridge", "instance_id": expected}


def test_goc1_variables_exclude_engine_control_and_physical_keys():
    params = [{"id": i} for i in ("wall", "target_part", "render_mode", "target_material",
                                  "slicer_speed", "mat_thick", "no_default")]
    got = goc1_variables(params, {"wall": 2, "target_part": "a", "target_material": "pla",
                                  "slicer_speed": 1, "mat_thick": 3})
    assert got == {"wall": 2, "mat_thick": 3, "no_default": None}


def test_standard_loader_ignores_files_without_a_key_and_reads_both_shapes():
    r = resolver()
    entries = r.by_type["standard"].entries()
    assert set(entries) == {"nema-17-48mm-test", "gt2-pulley-test", "elbow-test",
                            "motor-2207-test"}
    # `parameters` as a mapping (elbow) and `cdg_interfaces` instead of `interfaces` (motor)
    elbow = r.resolve(standard("e", "elbow-test", arm=80))
    assert elbow.interfaces["outlet"].frame.origin == (80.0, 80.0, 0.0)
    assert elbow.identity["parameters"] == {"arm": 80}
    motor = r.resolve(standard("m", "motor-2207-test"))
    assert motor.interfaces["base"].frame.part == "motor-2207-test"


def test_duplicate_standard_keys_are_reported(tmp_path):
    for name in ("a.json", "b.json"):
        shutil.copy(STANDARD / "gt2-pulley-test.json", tmp_path / name)
    report = validate_assembly(assembly([standard("p", "gt2-pulley-test")], []),
                               CompositeResolver.for_directories(None, tmp_path))
    assert any("defined twice" in f.message for f in report.errors)


# ── step 3: the mating rule ───────────────────────────────────────────────────
def test_polarity_must_be_complementary():
    doc = _pair(cartridge("b1"), cartridge("b2"), "b1.motor_face", "b2.motor_face")
    report = validate_assembly(doc, resolver())
    assert ("polarity", "m1") in codes(report) and ("size_key", "m1") not in codes(report)
    assert "a male vs b male" in report.errors[0].message
    assert ("unreachable", "b2") in codes(report)


def test_size_key_must_match(fpv_commons):
    shutil.copytree(COMMONS / "nema-bracket", fpv_commons / "nema-bracket")
    doc = _pair(cartridge("bracket"),
                cartridge("pod", slug="semantic-motor-mount", mode="soft_mount"),
                "bracket.motor_face", "pod.motor_bolt_pattern")
    report = validate_assembly(doc, resolver(commons=fpv_commons))
    assert ("size_key", "m1") in codes(report) and ("polarity", "m1") not in codes(report)
    assert "a 'nema-17-face' vs b 'motor-mount-16x16-m3'" in report.errors[0].message


def test_fpv_motor_on_a_soft_mount_pod(fpv_commons):
    """The pod's bolt-pattern face is at z = plate_thick + iso_gap = 4 + 2.4 = 6.4,
    normal +z, x = +x. The 2207 motor's base is at its origin with normal -z, x = +x, so
    H(F_motor) = Flip and T = T(0,0,6.4)·Flip·Rz(0)·Flip = T(0,0,6.4): the motor sits
    upright on the pod."""
    doc = _pair(cartridge("pod", slug="semantic-motor-mount", mode="soft_mount",
                          motor_pattern="16x16"),
                standard("motor", "motor-2207-test"), "pod.motor_bolt_pattern", "motor.base")
    report = validate_assembly(doc, resolver(commons=fpv_commons))
    assert report.ok, report.findings
    assert_matrix(report.placements["motor"],
                  ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 6.4), (0, 0, 0, 1)))


def test_a_select_driven_size_key_follows_the_parameter(fpv_commons):
    doc = _pair(cartridge("pod", slug="semantic-motor-mount", mode="soft_mount",
                          motor_pattern="9x9"),
                standard("motor", "motor-2207-test"), "pod.motor_bolt_pattern", "motor.base")
    report = validate_assembly(doc, resolver(commons=fpv_commons))
    assert ("size_key", "m1") in codes(report)
    assert "motor-mount-9x9-m2" in report.errors[0].message


def test_an_interface_with_no_frame_cannot_mate():
    doc = _pair(cartridge("b"), standard("m", "nema-17-48mm-test"), "b.mount_slot", "m.face")
    report = validate_assembly(doc, resolver())
    messages = [f.message for f in report.errors if f.subject == "m1"]
    assert any("declares no frame" in m for m in messages)
    assert any("declares no polarity" in m for m in messages)


def test_an_interface_on_a_part_the_mode_does_not_produce():
    doc = _pair(cartridge("b", mode="flat"), standard("m", "nema-17-48mm-test"),
                "b.wall_face", "m.face")
    report = validate_assembly(doc, resolver())
    assert any("sits on part 'angle_plate'" in f.message for f in report.errors)


def test_an_unknown_interface_lists_the_known_ones():
    doc = _pair(cartridge("b"), standard("m", "nema-17-48mm-test"), "b.motor_flange", "m.face")
    report = validate_assembly(doc, resolver())
    assert "has no interface 'motor_flange' (it has: motor_face, mount_slot, wall_face)" in (
        report.errors[0].message
    )


# ── step 6: reachability ──────────────────────────────────────────────────────
def test_an_unmated_component_is_unreachable_and_the_digest_still_computes():
    doc = assembly(
        [cartridge("bracket"), standard("motor", "nema-17-48mm-test"),
         standard("spare", "gt2-pulley-test")],
        [mate("m1", "bracket.motor_face", "motor.face")],
    )
    report = validate_assembly(doc, resolver())
    assert codes(report) == [("unreachable", "spare")]
    assert set(report.placements) == {"bracket", "motor"}
    assert report.digest and len(report.digest) == 64


# ── external designs ──────────────────────────────────────────────────────────
TOOLHEAD = {
    "id": "toolhead",
    "source": {
        "type": "external", "name": "Example toolhead", "license": "GPL-3.0",
        "url": "https://example.org/toolhead",
        "interfaces": [{"id": "motor_face", "polarity": "female", "size_key": "nema-17-face",
                        "symmetry": 4,
                        "frame": {"origin": [0, 0, 48], "normal": [0, 0, 1],
                                  "x_axis": [1, 0, 0]}}],
    },
}


def test_an_external_design_mates_through_its_declared_facts():
    doc = assembly([cartridge("bracket"), copy.deepcopy(TOOLHEAD)],
                   [mate("m1", "bracket.motor_face", "toolhead.motor_face")])
    report = validate_assembly(doc, resolver())
    assert report.ok, report.findings
    assert report.placements["toolhead"][2][3] == pytest.approx(53)
    identity = report.components["toolhead"].identity
    assert identity["type"] == "external" and identity["facts"]["license"] == "GPL-3.0"


# ── the resolver protocol: what a service implements ──────────────────────────
class InMemoryResolver:
    """What asset-shells does with stored submodels: build a manifest-shaped mapping
    and reuse resolve_interfaces, so the frame arithmetic is the keystone's."""

    def __init__(self, store):
        self.store = store

    def resolve(self, component):
        manifest = self.store[component["source"]["key"]]
        return ResolvedComponent(
            component_id=component["id"], source_type="standard", label="memory",
            identity={"type": "standard", "key": component["source"]["key"]},
            interfaces=resolve_interfaces(manifest, component["source"].get("parameters"),
                                          default_part="body"),
        )


def test_any_object_with_resolve_is_a_component_resolver():
    elbow = json.loads((STANDARD / "elbow-test.json").read_text())
    store = {"elbow-test": {"parameters": [{"id": "arm", "default": 50}],
                            "hyperobject": {"cdg_interfaces": elbow["interfaces"]}}}
    r = InMemoryResolver(store)
    assert isinstance(r, ComponentResolver)
    assert isinstance(ExternalResolver(), ComponentResolver)
    doc = assembly([standard("e1", "elbow-test"), standard("e2", "elbow-test")],
                   [mate("m1", "e1.outlet", "e2.inlet")])
    report = validate_assembly(doc, r)
    assert report.ok and report.placements["e2"][0][3] == pytest.approx(50)


# ── step 8: the digest ────────────────────────────────────────────────────────
def _external_only():
    second = copy.deepcopy(TOOLHEAD)
    second["id"] = "adapter"
    second["source"]["interfaces"][0].update(polarity="male", id="face")
    second["source"]["interfaces"][0]["frame"]["origin"] = [0, 0, 0]
    return assembly([copy.deepcopy(TOOLHEAD), second],
                    [mate("m1", "adapter.face", "toolhead.motor_face")])


#: Golden vector for `hyperobjects-assembly-v1` over a document whose identities need
#: no file (external designs only). A second implementation must reproduce it.
GOLDEN_EXTERNAL_DIGEST = "c6d62415bb2a2a4157ebba13f714db05070d21be71d8ff07563df03ae1368525"


def test_digest_golden_vector():
    report = validate_assembly(_external_only(), ExternalResolver())
    assert report.ok, report.findings
    assert report.digest == GOLDEN_EXTERNAL_DIGEST


def test_digest_is_independent_of_key_order_and_integral_float_spelling():
    a = validate_assembly(_external_only(), ExternalResolver()).digest
    doc = _external_only()
    doc["components"][0]["source"]["interfaces"][0]["frame"]["origin"] = [0.0, 0.0, 48.0]
    reordered = json.loads(json.dumps(dict(reversed(list(doc.items())))))
    assert validate_assembly(reordered, ExternalResolver()).digest == a


def test_digest_moves_with_parameters_files_and_catalog(tmp_path):
    shutil.copytree(COMMONS, tmp_path / "commons")
    shutil.copytree(STANDARD, tmp_path / "std")

    def digest(**bracket_params):
        doc = _pair(cartridge("bracket", **bracket_params),
                    standard("motor", "nema-17-48mm-test"), "bracket.motor_face", "motor.face")
        return validate_assembly(doc, resolver(tmp_path / "commons", tmp_path / "std")).digest

    base = digest()
    assert base == digest()
    # The document is hashed as written: stating a default changes the document (and
    # so the digest), but its spelling as 5 or 5.0 does not (GOC-1 §3.1).
    assert digest(plate_thick=5) == digest(plate_thick=5.0) != base
    assert digest(plate_thick=6) != digest(plate_thick=5)
    (tmp_path / "commons" / "nema-bracket" / "main.py").write_text("# changed\n")
    changed_tree = digest()
    assert changed_tree != base
    entry = json.loads((tmp_path / "std" / "nema-17-48mm-test.json").read_text())
    entry["name"]["en"] += " rev B"
    (tmp_path / "std" / "nema-17-48mm-test.json").write_text(json.dumps(entry))
    changed_catalog = digest()
    assert changed_catalog != changed_tree
    # A README is not part of the GOC-1 tree, so it does not move the digest.
    (tmp_path / "commons" / "nema-bracket" / "README.md").write_text("notes\n")
    assert digest() == changed_catalog


# ── step 7 and the CLI ────────────────────────────────────────────────────────
def test_collision_without_the_cad_kernel_is_unavailable_never_a_pass(monkeypatch):
    from y4d_spec.assembly import collision

    def missing():
        raise ImportError("no cadquery")

    monkeypatch.setattr(collision, "_cq", missing)
    report = validate_assembly(_external_only(), ExternalResolver(), collision=True)
    assert report.ok and report.collision == "unavailable"
    assert codes(report, "warning") == [("collision", None)]
    assert "no intersection was checked" in report.warnings[0].message


@pytest.mark.geometry
def test_collision_without_bodies_is_partial_never_a_pass():
    """External designs with no envelope have no solid: --collision (ASM-1 §3.7) names
    them and reports `partial`, never a pass."""
    report = validate_assembly(_external_only(), ExternalResolver(), collision=True)
    assert report.collision == "partial"
    assert codes(report, "warning") == [("collision-unchecked", None)]
    assert "declares no envelope" in report.warnings[0].message


def _write(tmp_path, doc):
    path = tmp_path / "assembly.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


def _cli(path, *extra):
    return main(["assembly", "check", path, "--commons", str(COMMONS),
                 "--standard-parts", str(STANDARD), *extra])


def test_cli_passing_assembly(tmp_path, capsys):
    doc = _pair(cartridge("bracket"), standard("motor", "nema-17-48mm-test"),
                "bracket.motor_face", "motor.face", rotation_index=1)
    assert _cli(_write(tmp_path, doc)) == 0
    out = capsys.readouterr().out
    assert "placement (world ← component, mm):" in out
    assert "t=(0.0000, 0.0000, 53.0000)" in out
    assert "180.000° about" in out
    assert "m1: bracket.motor_face ↔ motor.face  sym=4 θ=90° [tree]" in out
    assert "components=2 placed=2 mates=1 closed=1 errors=0 warnings=0 collision=not run" in out


def test_cli_json_and_failure_exit(tmp_path, capsys):
    doc = _pair(cartridge("bracket", plate_thick=12), standard("motor", "nema-17-48mm-test"),
                "bracket.motor_face", "motor.face")
    assert _cli(_write(tmp_path, doc), "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False and data["digest"] is None
    assert data["errors"][0]["subject"] == "bracket"


@pytest.mark.geometry  # --collision needs the CAD kernel
def test_cli_read_and_usage_errors(tmp_path, capsys):
    assert _cli(str(tmp_path / "missing.json")) == 2
    path = _write(tmp_path, _external_only())
    assert main(["assembly", "check", path, "--commons", str(tmp_path / "nope")]) == 2
    assert main(["assembly", "check", path, "--collision"]) == 0
    assert "collision=partial" in capsys.readouterr().out  # no envelopes: named, not passed


# ── robustness: never a traceback ─────────────────────────────────────────────
class _BrokenResolver:
    def resolve(self, component):
        raise KeyError("interfaces")


def test_a_resolver_bug_is_a_finding_not_a_crash():
    report = validate_assembly(assembly([standard("a", "elbow-test")], []), _BrokenResolver())
    assert codes(report) == [("resolve", "a")]
    assert "the resolver failed: KeyError" in report.errors[0].message


def test_a_slug_cannot_leave_the_commons_directory():
    component = cartridge("x")
    component["source"]["slug"] = "../escape"
    report = resolver().by_type["cartridge"]
    with pytest.raises(Exception, match="not a single directory name"):
        report.resolve(component)


def test_a_non_finite_angle_is_a_rotation_error_and_has_no_digest():
    doc = assembly(
        [standard("motor", "nema-17-48mm-test"), standard("pulley", "gt2-pulley-test")],
        [mate("m1", "motor.shaft", "pulley.bore", angle_deg=float("nan"))],
    )
    report = validate_assembly(doc, resolver())
    assert not report.ok and report.digest is None
    assert ("rotation", "m1") in codes(report) and ("digest", None) in codes(report)
    assert "pulley" not in report.placements
