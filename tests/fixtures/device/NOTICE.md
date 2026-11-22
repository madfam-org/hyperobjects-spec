# Device-control fixtures — provenance and licence

`candybar-handheld/` is a copy of the cartridge of the same name proposed to
[madfam-org/solid-hyperobjects](https://github.com/madfam-org/solid-hyperobjects)
(`LICENSE`, `NOTICE`, `main.py`, `project.json` and `candybar.graph.json`, byte for byte;
its `docs/` folder is left out). It is the first cartridge to carry a `device` block, and
the device-control tests (`tests/test_device_controls.py`) check it without a render and,
where the CAD kernel is installed, against the meshes it renders.

It is licensed **CERN-OHL-W-2.0** (see its `LICENSE` and `project.json`), not under this
repository's Apache-2.0, and is copied unmodified as a test input only. Do not edit it:
refresh it from the commons. The tests that need a broken declaration change a copy in
memory or in a temporary directory. Until the solid commons' `SPEC_PIN` reaches a keystone
with the device-control vocabulary, the copy and the commons cartridge must stay identical:
a change to one is made to the other in the same pair of pull requests.
