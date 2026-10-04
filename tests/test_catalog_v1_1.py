"""ASM-1 v1.1 catalog fixes (ruling D5), proven by placement rather than by inspection.

* bearing-608.outer_race: its normal was −z, which placed a 608 OUTSIDE a seat framed at
  its entrance (finding C1). It is +z now; the bearing must land inside the idler-608
  seat, whose cavity is z = 3..10 under an entrance frame at z = width = 10 (the frame
  solid-hyperobjects#118 authors on idler-608).
* fpv-frame-5in-x-225 motor mounts: x_axis points outward along each arm, so a clamp pod
  whose x_axis runs along its arm slot aligns at rotation_index 0 (the P4-AUTH-B finding).
* sma-bulkhead-jack: the male part between an antenna mount's Ø6.5 bore and the antenna's
  female coupling nut (the female↔female mate P4-AUTH-B could not make).
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

import hyperobjects_standard_parts
from hyperobjects_standard_parts import interface_frames, load_part, resolve_parameters
from y4d_spec.assembly import (
    CompositeResolver,
    ExternalResolver,
    StandardPartsResolver,
    validate_assembly,
)

CATALOG = Path(hyperobjects_standard_parts.__file__).parent / "parts"
AXIS_TYPES = ("socket", "thread", "threaded_socket", "hinge")


def _resolver(catalog=CATALOG):
    return CompositeResolver(standard=StandardPartsResolver(catalog), external=ExternalResolver())


def _external(cid, iface):
    return {"id": cid, "source": {"type": "external", "name": f"Test {cid}",
                                  "license": "CERN-OHL-W-2.0", "url": "https://example.org/x",
                                  "interfaces": [iface]}}


def _assembly(components, mates):
    return {
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "catalog-v1-1",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


# ── bearing-608 ───────────────────────────────────────────────────────────────
IDLER_SEAT = {  # idler-608 flat_idler_bearing_seat at its defaults (width = 10)
    "id": "seat", "polarity": "female", "size_key": "bearing-608", "symmetry": 0,
    "geometry_type": "socket",
    "frame": {"origin": [0, 0, 10], "normal": [0, 0, 1], "x_axis": [1, 0, 0]},
}


def test_a_608_lands_inside_the_idler_seat():
    doc = _assembly(
        [_external("idler", IDLER_SEAT), {"id": "bearing",
                                          "source": {"type": "standard", "key": "bearing-608"}}],
        [_mate("m1", "idler.seat", "bearing.outer_race", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    placed = report.placements["bearing"]
    face_a, face_b = _apply(placed, (0, 0, 0)), _apply(placed, (0, 0, 7))
    zs = sorted((face_a[2], face_b[2]))
    assert zs == pytest.approx([3.0, 10.0])  # the seat cavity, z = 3..10
    assert face_a[2] == pytest.approx(10.0)  # face A flush with the entrance
    # Both faces on the seat axis.
    assert face_a[:2] == pytest.approx((0.0, 0.0)) and face_b[:2] == pytest.approx((0.0, 0.0))


def test_the_old_608_normal_put_the_bearing_outside_the_seat(tmp_path):
    """The regression this fixes: with normal −z the bearing sat at z = 10..17."""
    import json

    entry = load_part("bearing-608")
    entry["interfaces"][0]["frame"]["normal"] = [0, 0, -1]
    (tmp_path / "bearing-608.json").write_text(json.dumps(entry))
    resolver = _resolver(tmp_path)
    doc = _assembly(
        [_external("idler", IDLER_SEAT), {"id": "bearing",
                                          "source": {"type": "standard", "key": "bearing-608"}}],
        [_mate("m1", "idler.seat", "bearing.outer_race", angle_deg=0)],
    )
    report = validate_assembly(doc, resolver)
    assert report.ok, report.findings  # closure cannot see it: only placement can
    placed = report.placements["bearing"]
    zs = sorted(_apply(placed, (0, 0, z))[2] for z in (0, 7))
    assert zs == pytest.approx([10.0, 17.0])


def test_axis_interfaces_put_the_body_on_the_side_their_polarity_says():
    """The audit of every axis-type interface in the catalog (C1's class of mistake):

    a female bore/thread runs INTO the material, away from the partner (body on the
    −normal side); a male shaft/body runs TOWARD the partner (+normal side). Each entry's
    body extent along the axis is read from its own frame convention below.
    """
    body_side = {  # key.interface: sign of the body/feature along the normal from the origin
        "bearing-608.outer_race": +1,   # body z 0..7, normal +z
        "bearing-608.bore": -1,         # bore z 0..7 under origin z = 7, normal +z
        "extrusion-2020.end_a": -1,     # tap runs +z from end A, normal −z
        "extrusion-2020.end_b": -1,     # tap runs −z from end B, normal +z
        "gt2-pulley-20t-5mm.bore": -1,  # bore runs +z from face A, normal −z
        "motor-2207.prop_shaft": +1,    # shaft continues +z past the prop seat
        "nema-17-48mm.shaft": +1,       # shaft continues +z past its seat
        "prop-5in.hub": -1,             # hub hole runs +z from the bottom face, normal −z
        "vtx-antenna-sma.connector": -1,  # nut cavity runs +z, normal −z
        "sma-bulkhead-jack.panel": +1,     # threaded body runs +z from the shoulder
        "sma-bulkhead-jack.coupling": -1,  # the plug's nut covers the thread behind the
                                           # reference plane — a mated face, see note
    }
    seen = set()
    for key in hyperobjects_standard_parts.list_part_keys():
        part = load_part(key)
        for iface in part["interfaces"]:
            if iface["geometry_type"] not in AXIS_TYPES:
                continue
            name = f"{key}.{iface['id']}"
            if name.startswith("fpv-"):
                continue  # mid-plane origins (camera, bay): no body side to check
            seen.add(name)
            assert name in body_side, f"{name}: add it to the audit"
            if name == "sma-bulkhead-jack.coupling":
                continue
            expected = {"male": +1, "female": -1}[iface["polarity"]]
            assert body_side[name] == expected, name
    assert seen == set(body_side)


# ── fpv-frame-5in-x-225 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("given", [{}, {"motor_half_x_mm": 60, "motor_half_y_mm": 100}])
def test_motor_mount_x_axis_points_outward_along_the_arm(given):
    part = load_part("fpv-frame-5in-x-225")
    frames = interface_frames(part, resolve_parameters(part, given))
    for corner in ("fl", "fr", "rl", "rr"):
        f = frames[f"motor_mount_{corner}"]
        arm = math.hypot(f.origin[0], f.origin[1])
        assert f.x_axis == pytest.approx((f.origin[0] / arm, f.origin[1] / arm, 0.0), abs=1e-15)
        assert math.hypot(*f.x_axis) == pytest.approx(1.0, abs=1e-12)


def test_a_clamp_pod_aligns_with_a_45_degree_arm_at_rotation_index_0():
    pod = {"id": "arm_clamp", "polarity": "female", "size_key": "motor-mount-16x16-m3",
           "symmetry": 4,
           "frame": {"origin": [0, 0, -9], "normal": [0, 0, -1], "x_axis": [1, 0, 0]}}
    doc = _assembly(
        [{"id": "frame", "source": {"type": "standard", "key": "fpv-frame-5in-x-225"}},
         _external("pod", pod)],
        [_mate("m1", "frame.motor_mount_fl", "pod.arm_clamp", rotation_index=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    placed = report.placements["pod"]
    pod_x = (placed[0][0], placed[1][0], placed[2][0])  # the pod's +x (its arm slot) in world
    assert pod_x == pytest.approx((math.sqrt(0.5), math.sqrt(0.5), 0.0), abs=1e-9)


# ── sma-bulkhead-jack ─────────────────────────────────────────────────────────
MOUNT_BORE = {  # an antenna mount's Ø6.5 bore, framed at its entrance (fpv-antenna-mount)
    "id": "sma_bore", "polarity": "female", "size_key": "sma-bulkhead", "symmetry": 0,
    "geometry_type": "thread",
    "frame": {"origin": [0, 0, 0], "normal": [0, 0, 1], "x_axis": [1, 0, 0]},
}


def test_mount_jack_antenna_chain_closes():
    doc = _assembly(
        [_external("mount", MOUNT_BORE),
         {"id": "jack", "source": {"type": "standard", "key": "sma-bulkhead-jack"}},
         {"id": "antenna", "source": {"type": "standard", "key": "vtx-antenna-sma"}}],
        [_mate("m1", "mount.sma_bore", "jack.panel", angle_deg=0),
         _mate("m2", "jack.coupling", "antenna.connector", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    # The jack's body runs into the bore (world −z); the antenna couples at the mating
    # face, 10 mm (mating_face_z_mm) through, and points on along the same axis.
    jack = report.placements["jack"]
    assert _apply(jack, (0, 0, 10))[2] == pytest.approx(-10.0)
    antenna = report.placements["antenna"]
    assert _apply(antenna, (0, 0, 0))[2] == pytest.approx(-10.0)
    assert _apply(antenna, (0, 0, 60))[2] == pytest.approx(-70.0)


def test_the_direct_mount_to_antenna_mate_is_still_refused():
    """Female↔female: why the jack exists."""
    doc = _assembly(
        [_external("mount", MOUNT_BORE),
         {"id": "antenna", "source": {"type": "standard", "key": "vtx-antenna-sma"}}],
        [_mate("m1", "mount.sma_bore", "antenna.connector", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "polarity" for f in report.errors)


def test_jack_mating_face_follows_its_parameter():
    part = load_part("sma-bulkhead-jack")
    frames = interface_frames(part, resolve_parameters(part, {"mating_face_z_mm": 14}))
    assert frames["coupling"].origin == (0.0, 0.0, 14.0)
    assert frames["panel"].origin == (0.0, 0.0, 0.0)


def test_a_catalog_let_cycle_or_shadow_is_refused():
    from hyperobjects_standard_parts.check import check_part

    part = copy.deepcopy(load_part("fpv-frame-5in-x-225"))
    part["interfaces"][0]["let"] = {"arm_mm": "arm_mm + 1"}
    assert any("dependency cycle" in p for p in check_part(part, name=part["key"]))
    part["interfaces"][0]["let"] = {"motor_half_x_mm": "1"}
    assert any("shadows a parameter" in p for p in check_part(part, name=part["key"]))
