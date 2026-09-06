"""`_export_stl` must not route an assembly through the deprecated `Assembly.save`.

22 of the ~500 commons cartridges return a `cq.Assembly` rather than a `cq.Workplane`
(bag-feet, bevel-gear, button-hook-aid, chicago-screw, fascinator-base, gear-rack,
hat-size-reducer, headband-blank, hook-and-eye, invisible-zipper, kiss-lock-frame,
magnetic-button-cover, planetary-gearset, strap-buckle, tpu-chainmail-panel,
tpu-lattice-panel, tpu-scale-mail, twist-lock-closure, veil-comb, worm-gear,
zipper-loop-aid, zipper) — every one of them renders through the assembly arm of
`_export_stl`. That arm used to call `Assembly.save`, which CadQuery 2.7 marks
`@deprecate()`: "will be removed in the next release". The whole fleet's renders would
have gone red together at the next kernel bump, so the arm now flattens with
`toCompound()` and hands the compound to the same `cq.exporters.export` the Workplane
arm uses.

`test_assembly_export_survives_assembly_save_removal` is the gate that keeps it that
way: it deletes the deprecated entry point (monkeypatched to raise) and requires the
export to succeed anyway. A regression to `save` fails it immediately rather than in
whatever release drops the method.

The two paths are the SAME tessellation, not merely a close one, which is why the
identity check below is exact rather than tolerant. `Assembly.save` forwards to
`Assembly.export`, whose STL arm is
`self.toCompound().exportStl(path, tolerance, angularTolerance, ascii)`; `exporters.export`
calls `shape.exportStl(fname, tolerance, angularTolerance, useascii)`. Same method, same
compound, same defaults (0.1 / 0.1 / binary). Observed byte-identical on the real
`zipper` cartridge (`closed/tape_left`, 36 bodies, sha256 05a22cc0…, 2 163 284 bytes);
`test_tocompound_export_is_byte_identical_to_assembly_save` re-proves it in-suite on a
fixture, for as long as `save` still exists to compare against.
"""

import hashlib
import warnings

import pytest

pytest.importorskip("cadquery")
pytest.importorskip("trimesh")

import cadquery as cq  # noqa: E402

from y4d_spec.geometry import _export_stl, _judge_stl  # noqa: E402

pytestmark = pytest.mark.geometry


def _assembly():
    """A three-member assembly with the members apart, so bodies == members.

    Placed apart on purpose: a mesh-level body count is only a meaningful witness of
    "the whole tree got exported" when the members do not fuse into one component.
    """
    bar = cq.Workplane("XY").box(20, 4, 4)
    peg = cq.Workplane("XY").cylinder(6, 2)
    return (
        cq.Assembly()
        .add(bar, name="bar")
        .add(peg, name="peg_a", loc=cq.Location(cq.Vector(40, 0, 0)))
        .add(peg, name="peg_b", loc=cq.Location(cq.Vector(-40, 0, 0)))
    )


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verdict(path):
    """The render gate's own reading of the file — same bar every cartridge faces."""
    return _judge_stl(
        str(path),
        mode="test",
        part="whole",
        preset=None,
        printability=False,
    )


def _evidence(check):
    """The judgeable facts, rounded to the STL's own float32 grain."""
    return (
        check.ok,
        check.bodies,
        check.watertight,
        round(check.volume, 4),
        tuple(round(e, 4) for e in check.extents),
    )


def test_assembly_export_survives_assembly_save_removal(tmp_path, monkeypatch):
    """The gate: with `Assembly.save` gone, an assembly still exports and still judges.

    `save` is monkeypatched to raise rather than merely counted, so this fails on a
    regression to it even if the STL somehow still appeared.
    """
    def _gone(*_args, **_kwargs):
        raise AssertionError(
            "_export_stl called the deprecated Assembly.save — it must flatten with "
            "toCompound() and export the compound instead"
        )

    monkeypatch.setattr(cq.Assembly, "save", _gone, raising=True)

    out = tmp_path / "no-save.stl"
    _export_stl(_assembly(), str(out))

    assert out.exists() and out.stat().st_size > 0
    check = _verdict(out)
    assert check.ok, check.problems
    assert check.bodies == 3, "all three members must be in the mesh, not just the root"
    assert check.volume > 0
    assert check.watertight


def test_tocompound_export_is_byte_identical_to_assembly_save(tmp_path):
    """The change is a swap of entry point, not of tessellation.

    Kept as a live comparison for as long as CadQuery still ships `save`; it is expected
    to disappear with the method, at which point the gate above is the one that matters.
    """
    if not hasattr(cq.Assembly, "save"):  # pragma: no cover — future CadQuery
        pytest.skip("cq.Assembly.save has been removed; nothing left to compare against")

    baseline = tmp_path / "baseline-save.stl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the deprecation is the point of this PR
        _assembly().save(str(baseline), "STL")

    ours = tmp_path / "ours-tocompound.stl"
    _export_stl(_assembly(), str(ours))

    assert _sha256(ours) == _sha256(baseline)
    assert ours.stat().st_size == baseline.stat().st_size
    assert _evidence(_verdict(ours)) == _evidence(_verdict(baseline))


def test_workplane_export_is_untouched(tmp_path):
    """The Workplane arm is the same one line it always was."""
    out = tmp_path / "plain.stl"
    _export_stl(cq.Workplane("XY").box(10, 10, 10), str(out))

    check = _verdict(out)
    assert check.ok, check.problems
    assert check.bodies == 1
    assert check.volume == pytest.approx(1000.0, rel=1e-3)
