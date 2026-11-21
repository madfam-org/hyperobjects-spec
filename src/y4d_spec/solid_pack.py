"""The solid node pack: Yantra4D's graph engine behind the core's node-pack interface.

RFC 0067 puts the kernel-neutral half of the graph in ``hyperobject_graph`` and leaves
each kernel its own vocabulary. The solid vocabulary is the vendored platform engine
(``y4d_spec.graph``, byte-identical to Yantra4D's ``graph_engine.py``): 23 node types,
``solid`` and ``profile`` sockets, CadQuery out. This module is the adapter, and it is
deliberately thin, because the engine's emission must not change by passing through it:

* the **catalogue** is read from the vendored ``graph-node-catalog.json`` — the file the
  engine generates from its own ``NODE_TYPES`` — so the pack never describes a node twice;
* ``transpile`` **is** the engine's ``transpile``, called with the document the core hands
  it. For a 1.0 or 1.1 graph that document is the file's own, key for key
  (``hyperobject_graph.pack_document``), so the program is byte-identical to calling the
  engine directly. ``tests/test_graph_core_solid.py`` proves it for every graph in the
  solid commons;
* the **script contract** is the two languages the keystone already renders, each with the
  suffixes its render path accepts, and ``target_part`` as the part parameter — the name
  the platform's runner injects (``cq_runner.py``) and the engine reads.

The engine's own validation still runs inside ``transpile``: the core checks what is
kernel-neutral (cycles, sockets, references, expressions, declarations), the engine what
is geometric (value ranges, a revolve axis in its profile's plane).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from hyperobject_graph import ScriptContract, catalogue_from_json

from .graph import graph_engine

_CATALOG = Path(graph_engine.__file__).with_name("graph-node-catalog.json")

#: The names the emitted program defines or the runner injects (the engine's
#: ``_RESERVED_IDENTIFIERS``): a parameter, a derived value or a binding may not shadow
#: them.
RESERVED = frozenset(graph_engine._RESERVED_IDENTIFIERS)

#: What the keystone's sandbox runs for a script node, and under what suffixes — the
#: suffix gates of the CadQuery and OpenSCAD render paths.
SCRIPT_CONTRACT = ScriptContract(
    languages={"cadquery": (".py", ".cq"), "openscad": (".scad",)},
    outputs=("solid",),
    part_parameter="target_part",
    # The CadQuery runner puts these in every source's globals before the parameters;
    # a binding of the same name would overwrite the module the source expects.
    reserved=frozenset({"cq", "math"}),
)


@cache
def _catalogue():
    return catalogue_from_json(json.loads(_CATALOG.read_text(encoding="utf-8")))


class SolidPack:
    """``hyperobject_graph.NodePack`` for the solid commons."""

    kernel = "solid"
    name = "yantra4d-solid"
    socket_types = frozenset({"solid", "profile"})
    output_types = frozenset({"solid"})
    # A profile holds pending CadQuery wires that its first consumer takes; a second
    # consumer fails at render, so the engine refuses it and so does the core.
    fan_out = {"profile": 1}
    reserved_identifiers = RESERVED
    script = SCRIPT_CONTRACT
    # The vendored engine has no `script` node yet: a wrapper is rendered by invoking its
    # source, and a script node inside a native graph waits for RFC 0067 P5.
    embedded_scripts = False

    @property
    def version(self) -> str:
        """The vocabulary's identity: the sha256 of the vendored engine, as locked."""
        lock = json.loads(_CATALOG.with_name("graph.lock.json").read_text(encoding="utf-8"))
        return "engine-" + lock["hashes"]["graph_engine.py"][:12]

    def catalogue(self):
        return _catalogue()[0]

    def param_kinds(self):
        return _catalogue()[1]

    def transpile(self, pack_doc: dict, bindings: dict, source_name: str) -> str:
        return graph_engine.transpile(pack_doc, bindings, source_name=source_name)


SOLID_PACK = SolidPack()

__all__ = ["RESERVED", "SCRIPT_CONTRACT", "SOLID_PACK", "SolidPack"]
