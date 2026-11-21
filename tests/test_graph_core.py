"""The graph core: validation, the node-pack interface, declarations and the script node.

Kernel-neutral by construction, so most of this runs against a small SHEET pack defined
here — a vocabulary with no CadQuery in it — and the solid pack is exercised where the
point is agreement with the engine. A rule that only worked for the solid vocabulary
would show up as a failure on the toy pack first.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

import hyperobject_graph as core
from hyperobject_graph import (
    GraphCoreError,
    NodeSpec,
    ParamKind,
    ParamSpec,
    ScriptContract,
    SocketSpec,
)
from y4d_spec.graph import graph_engine as ge
from y4d_spec.solid_pack import SOLID_PACK

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = json.loads(
    (Path(core.__file__).parent / "graph-core.schema.json").read_text(encoding="utf-8")
)


class SheetPack:
    """A toy sheet vocabulary: a sheet, a crease pattern, a fold. No geometry at all."""

    kernel = "sheet"
    name = "toy-sheet"
    version = "0"
    socket_types = frozenset({"sheet", "creases", "folded"})
    output_types = frozenset({"folded", "sheet"})
    fan_out = {"creases": 1}
    reserved_identifiers = frozenset({"doc"})
    script = ScriptContract(languages={"pliego-python": (".py",)}, outputs=("folded",),
                            part_parameter="target_part", reserved=frozenset({"pliego"}))
    embedded_scripts = False

    def catalogue(self):
        return {
            "sheet": NodeSpec("sheet", "sheet", params={
                "w": ParamSpec("length", 100.0, bindable=True, expr=True),
                "h": ParamSpec("length", 100.0, bindable=True, expr=True),
                "stock": ParamSpec("stock", "kraft"),
            }),
            "valley": NodeSpec("valley", "creases", params={
                "at": ParamSpec("length", 50.0, bindable=True, expr=True),
            }, inputs={"sheet": SocketSpec("sheet")}),
            "fold": NodeSpec("fold", "folded", params={
                "angle": ParamSpec("angle", 90.0, bindable=True, expr=True),
            }, inputs={"creases": SocketSpec("creases"),
                       "guide": SocketSpec("sheet", required=False)}),
        }

    def param_kinds(self):
        return {
            "length": ParamKind("length", True, True, "number (mm)"),
            "angle": ParamKind("angle", True, True, "number (deg)"),
            "stock": ParamKind("stock", False, False, "stock card id"),
        }

    def transpile(self, pack_doc, bindings, source_name):
        return json.dumps({"program": [n["type"] for n in pack_doc["nodes"]],
                           "bound": sorted(f"{k[0]}.{k[1]}" for k in bindings)})


SHEET = SheetPack()


def sheet_doc(**extra) -> dict:
    doc = {
        "version": "1.2.0",
        "kernel": "sheet",
        "nodes": [
            {"id": "blank", "type": "sheet", "params": {"w": 120.0}},
            {"id": "crease", "type": "valley", "inputs": {"sheet": "blank"},
             "params": {"at": {"expr": "half"}}},
            {"id": "card", "type": "fold", "inputs": {"creases": "crease"}},
        ],
        "outputs": {"card": "card"},
        "parameters": {"width": {"default": 120}},
        "derived": [{"id": "half", "expr": "width / 2"}],
    }
    doc.update(extra)
    return doc


def codes(problems) -> list[str]:
    return sorted({p.code for p in problems})


# ── The interface ──────────────────────────────────────────────────────────────


def test_both_packs_satisfy_the_protocol():
    assert isinstance(SOLID_PACK, core.NodePack)
    assert isinstance(SHEET, core.NodePack)


def test_a_valid_sheet_graph_has_no_problems_and_transpiles_through_its_pack():
    doc = sheet_doc()
    assert core.validate(doc, SHEET) == []
    program = json.loads(core.transpile(doc, SHEET))
    assert program["program"] == ["sheet", "valley", "fold"]


def test_the_pack_never_sees_the_core_only_keys():
    doc = sheet_doc(licence={"spdx": "CERN-OHL-W-2.0"})
    seen = {}

    class Spy(SheetPack):
        def transpile(self, pack_doc, bindings, source_name):
            seen.update(pack_doc)
            return ""

    core.transpile(doc, Spy())
    assert "licence" not in seen and "kernel" not in seen
    assert seen["nodes"] == doc["nodes"]


def test_export_catalogue_is_neutral_json_with_the_script_node():
    exported = core.export_catalogue(SHEET)
    json.dumps(exported)
    assert exported["kernel"] == "sheet"
    assert exported["nodes"]["fold"]["inputs"]["guide"] == {"type": "sheet", "required": False}
    assert exported["nodes"]["script"]["output"] == {"one_of": ["folded"]}


def test_solid_catalogue_is_the_engines_vocabulary():
    cat = SOLID_PACK.catalogue()
    assert set(cat) == set(ge.NODE_TYPES)
    for name, spec in ge.NODE_TYPES.items():
        assert cat[name].output == spec["output"]
        assert {s: i.type for s, i in cat[name].inputs.items()} == spec["inputs"]
        assert {p: (s.kind, s.default) for p, s in cat[name].params.items()} == {
            p: (k, d) for p, (k, d) in spec["params"].items()
        }
    assert set(SOLID_PACK.param_kinds()) == set(ge.PARAM_KINDS)
    assert SOLID_PACK.reserved_identifiers == ge._RESERVED_IDENTIFIERS


# ── Graph rules ────────────────────────────────────────────────────────────────


def test_cycle():
    doc = sheet_doc()
    doc["nodes"][0] = {"id": "blank", "type": "fold", "inputs": {"creases": "crease"}}
    doc["nodes"][1]["inputs"] = {"sheet": "blank"}
    assert "cycle" in codes(core.validate(doc, SHEET))


def test_self_reference_is_a_cycle():
    doc = sheet_doc()
    doc["nodes"][1]["inputs"] = {"sheet": "crease"}
    assert "cycle" in codes(core.validate(doc, SHEET))


def test_socket_type_mismatch():
    doc = sheet_doc()
    doc["nodes"][2]["inputs"] = {"creases": "blank"}  # a sheet where creases belong
    assert "socket-type" in codes(core.validate(doc, SHEET))


def test_dangling_reference_in_inputs_outputs_and_bindings():
    doc = sheet_doc()
    doc["nodes"][2]["inputs"] = {"creases": "ghost"}
    doc["outputs"]["extra"] = "nobody"
    problems = core.validate(doc, SHEET, parameters=[{"id": "w2", "binding": "phantom.w"}])
    assert sum(p.code == "dangling-ref" for p in problems) == 3


def test_unbound_required_input_and_optional_socket():
    doc = sheet_doc()
    doc["nodes"][2]["inputs"] = {}
    problems = core.validate(doc, SHEET)
    assert [p.where for p in problems if p.code == "unbound-input"] == [
        "/nodes/card/inputs/creases"
    ]
    # the optional socket may stay empty, and may be connected
    doc = sheet_doc()
    doc["nodes"][2]["inputs"]["guide"] = "blank"
    assert core.validate(doc, SHEET) == []


def test_fan_out_limit():
    doc = sheet_doc()
    doc["nodes"].append({"id": "card2", "type": "fold", "inputs": {"creases": "crease"}})
    doc["outputs"]["card2"] = "card2"
    assert "fan-out" in codes(core.validate(doc, SHEET))


def test_output_type_must_be_a_part_type():
    doc = sheet_doc()
    doc["outputs"]["crease"] = "crease"
    assert "socket-type" in codes(core.validate(doc, SHEET))


def test_unknown_type_param_socket_and_duplicate_id():
    doc = sheet_doc()
    doc["nodes"].append({"id": "x", "type": "teleport"})
    doc["nodes"].append({"id": "blank", "type": "sheet"})
    doc["nodes"][0]["params"]["colour"] = 3
    doc["nodes"][1]["inputs"]["extra"] = "blank"
    messages = " | ".join(p.message for p in core.validate(doc, SHEET))
    for needle in ("unknown node type 'teleport'", "duplicate node id 'blank'",
                   "unknown params for 'sheet'", "unknown input sockets"):
        assert needle in messages


def test_kernel_must_match_the_pack_and_be_declared_in_1_2():
    assert "kernel" in codes(core.validate(sheet_doc(kernel="soft"), SHEET))
    doc = sheet_doc()
    del doc["kernel"]
    assert "kernel" in codes(core.validate(doc, SHEET))


def test_core_keys_need_format_1_2():
    doc = sheet_doc(version="1.1.0")
    problems = core.validate(doc, SHEET)
    assert any("need format 1.2" in p.message for p in problems)


# ── Expressions ────────────────────────────────────────────────────────────────


def test_expression_reading_an_undeclared_name():
    doc = sheet_doc()
    doc["nodes"][0]["params"]["h"] = {"expr": "height * 2"}
    assert any("height" in p.message for p in core.validate(doc, SHEET)
               if p.code == "expression")


def test_unread_declaration():
    doc = sheet_doc()
    doc["parameters"]["spare"] = {"default": 1}
    assert "unread-declaration" in codes(core.validate(doc, SHEET))


def test_expression_where_the_kind_takes_none():
    doc = sheet_doc()
    doc["nodes"][0]["params"]["stock"] = {"expr": "width"}
    assert any("take literal values" in p.message for p in core.validate(doc, SHEET))


def test_derived_order_is_enforced():
    doc = sheet_doc(derived=[{"id": "a", "expr": "b + 1"}, {"id": "b", "expr": "width"}])
    doc["nodes"][1]["params"]["at"] = {"expr": "a"}
    assert "expression" in codes(core.validate(doc, SHEET))


def test_binding_rules():
    doc = sheet_doc()
    problems = core.validate(doc, SHEET, parameters=[
        {"id": "s", "binding": "blank.stock"},     # not bindable
        {"id": "a", "binding": "crease.at"},       # carries an expression too
        {"id": "z", "binding": "blank.zz"},        # no such param
    ])
    messages = " | ".join(p.message for p in problems)
    assert "cannot be bound" in messages
    assert "also carries an expression" in messages
    assert "has no param 'zz'" in messages


def test_reserved_identifiers_come_from_the_pack():
    doc = sheet_doc(parameters={"doc": {"default": 1}})
    doc["derived"] = [{"id": "half", "expr": "doc / 2"}]
    assert "identifier" in codes(core.validate(doc, SHEET))


# ── Declarations, i18n, licence, provenance ────────────────────────────────────


def declared_doc() -> dict:
    doc = sheet_doc()
    doc["declarations"] = {
        "parameters": [
            {"id": "width", "type": "slider", "default": 120, "min": 60, "max": 200,
             "label": {"en": "Width", "es": "Ancho"}, "group": "size"},
            {"id": "panel_w", "type": "slider", "default": 100,
             "label": "Panel", "binding": "blank.w", "group": "size"},
        ],
        "parameter_groups": [{"id": "size", "label": {"en": "Size", "es": "Tamaño",
                                                       "fr": "Taille", "pt": "Tamanho"}}],
        "presets": [{"id": "wide", "label": {"en": "Wide"}, "values": {"width": 180}}],
        "constraints": [{"expression": "width > panel_w", "severity": "error",
                         "message": {"en": "Width must exceed the panel"}}],
        "interfaces": [{"id": "edge", "label": {"en": "Edge"}, "parameters": ["width"],
                        "node": "card"}],
    }
    doc["nodes"][0]["params"] = {}
    doc["licence"] = {"spdx": "CERN-OHL-W-2.0"}
    return doc


def test_a_fully_declared_graph_is_valid():
    assert core.validate(declared_doc(), SHEET) == []


def test_declaration_problems():
    doc = declared_doc()
    decl = doc["declarations"]
    decl["parameters"].append({"id": "orphan", "type": "slider", "default": 1,
                               "label": {"en": "Orphan"}})
    decl["parameters"].append({"id": "width", "type": "dial", "label": {"es": "sin en"}})
    decl["presets"][0]["values"]["ghost"] = 1
    decl["constraints"].append({"expression": "min(width, 3) > 0"})
    decl["constraints"].append({"expression": "ghost > 0", "severity": "fatal"})
    decl["interfaces"][0]["node"] = "nowhere"
    decl["parameters"][1]["group"] = "nope"
    problems = core.validate(doc, SHEET)
    messages = " | ".join(str(p) for p in problems)
    for needle in ("orphan", "duplicate parameter id", "'dial'", "needs a 'default'",
                   "needs a label", "['ghost'], which are not declared parameters",
                   "unsupported token", "severity must be", "'nowhere'", "group 'nope'"):
        assert needle in messages, needle


def test_intentionally_unused_needs_a_reason_and_then_allows():
    doc = declared_doc()
    doc["declarations"]["parameters"].append({
        "id": "reserved_knob", "type": "slider", "default": 1, "label": "Knob",
        "intentionally_unused": {"reason": "kept for the mode not yet written"},
    })
    assert core.validate(doc, SHEET) == []
    doc["declarations"]["parameters"][-1]["intentionally_unused"] = {"reason": " "}
    assert "dead-parameter" in codes(core.validate(doc, SHEET))


def test_expression_scope_must_be_declared_when_there_are_declarations():
    doc = declared_doc()
    doc["declarations"]["parameters"] = doc["declarations"]["parameters"][1:]
    doc["declarations"]["constraints"] = []
    doc["declarations"]["interfaces"] = []
    doc["declarations"]["presets"] = []
    assert any("does not declare" in p.message for p in core.validate(doc, SHEET))


def test_label_keys_and_i18n_gaps():
    doc = declared_doc()
    doc["nodes"][2]["meta"] = {"label": {"en": "Card", "es": "Tarjeta", "fr": "Carte",
                                         "pt": "Cartão"}}
    keys = core.label_keys(doc)
    assert keys["parameters.width.label"] == {"en": "Width", "es": "Ancho"}
    assert "parameter_groups.size.label" in keys
    assert "presets.wide.label" in keys and "constraints.0.message" in keys
    assert "interfaces.edge.label" in keys and "nodes.card.label" in keys
    gaps = dict.fromkeys(core.i18n_gaps(doc))
    assert ("parameters.width.label", "fr") in gaps
    assert ("parameters.panel_w.label", "es") in gaps  # a plain string is English only
    assert not any(key == "parameter_groups.size.label" for key, _ in gaps)
    assert not any(key == "nodes.card.label" for key, _ in gaps)


def test_manifest_projection_is_a_copy_of_the_declared_lists():
    doc = declared_doc()
    projection = core.manifest_projection(doc)
    assert projection == doc["declarations"]
    projection["parameters"].clear()
    assert doc["declarations"]["parameters"]


def test_licence_and_provenance_shapes():
    doc = declared_doc()
    doc["licence"] = {"spdx": "not; a licence"}
    doc["provenance"] = {"authored": "generated", "sources": [
        {"path": "../escape.py", "sha256": "abc", "role": "magic"},
    ]}
    messages = " | ".join(str(p) for p in core.validate(doc, SHEET))
    for needle in ("SPDX", "names its generator", "inside the cartridge",
                   "64 lowercase hex", "role must be"):
        assert needle in messages


def test_source_digest_problems():
    import hashlib

    data = b"print('hi')\n"
    doc = {"provenance": {"sources": [
        {"path": "a.py", "sha256": hashlib.sha256(data).hexdigest(), "role": "script"},
        {"path": "b.py", "sha256": "0" * 64, "role": "script"},
        {"path": "gone.py", "sha256": "0" * 64, "role": "reference"},
    ]}}
    files = {"a.py": data, "b.py": b"changed"}
    problems = core.source_digest_problems(doc, files.get)
    assert [p.code for p in problems] == ["source-drift", "provenance"]


# ── The script node ────────────────────────────────────────────────────────────


def wrapper_doc(**bind_extra) -> dict:
    doc = declared_doc()
    doc["nodes"] = [{
        "id": "body", "type": "script",
        "params": {"source": "card.py", "language": "pliego-python", "output": "folded",
                   "bind": {"width": {"param": "width"}, "panel_w": {"param": "panel_w"},
                            **bind_extra}},
    }]
    doc["outputs"] = {"card": "body", "sleeve": "body"}
    doc["parameters"] = {}
    doc["derived"] = []
    doc["declarations"]["parameters"][1].pop("binding")
    doc["declarations"]["interfaces"][0]["node"] = "body"
    doc["provenance"] = {"authored": "hand", "sources": [
        {"path": "card.py", "sha256": "0" * 64, "role": "script"}]}
    return doc


def test_a_wrapper_is_valid_and_has_a_plan():
    doc = wrapper_doc()
    assert core.validate(doc, SHEET) == []
    plan = core.wrapper_plan(doc, SHEET)
    assert plan.source == "card.py" and plan.parts == ("card", "sleeve")


def test_pass_through_keeps_types_and_leaves_absent_absent():
    doc = wrapper_doc(style="round", scale=2)
    plan = core.wrapper_plan(doc, SHEET)
    got = plan.script_params({"width": "150", "target_part": "card", "stray": 1})
    assert got == {"width": "150", "style": "round", "scale": 2, "target_part": "card"}
    assert "panel_w" not in got  # nothing injected → the source's own fallback applies


def test_expression_binding_reads_the_scope_with_defaults():
    doc = wrapper_doc(half={"expr": "w2 / 2"})
    doc["parameters"] = {"width": {"default": 120}}
    doc["derived"] = [{"id": "w2", "expr": "width"}]
    assert core.validate(doc, SHEET) == []
    plan = core.wrapper_plan(doc, SHEET)
    assert plan.script_params({})["half"] == 60.0
    assert plan.script_params({"width": 200})["half"] == 100.0


def test_script_node_contract_violations():
    doc = wrapper_doc(target_part={"param": "width"}, pliego=1,
                      ghost={"param": "nope"}, odd=[1, 2])
    node = doc["nodes"][0]
    node["params"].update(source="../up.py", language="cobol", output="sheet", extra=1)
    node["inputs"] = {"x": "body"}
    messages = " | ".join(str(p) for p in core.validate(doc, SHEET))
    for needle in ("unknown params", "language 'cobol'", "plain relative path",
                   "output 'sheet'", "'inputs' must be empty", "part parameter",
                   "runner defines", "does not declare", "a binding is"):
        assert needle in messages, needle


def test_script_node_needs_1_2_and_a_contract():
    doc = wrapper_doc()
    no_scripts = SheetPack()
    no_scripts.script = None
    assert "script-node" in codes(core.validate(doc, no_scripts))
    old = {"version": "1.1.0", "nodes": [{"id": "s", "type": "script", "params": {}}],
           "outputs": {"p": "s"}}
    assert "script-node" in codes(core.validate(old, SHEET))


def test_suffix_must_match_the_language():
    doc = wrapper_doc()
    doc["nodes"][0]["params"]["source"] = "card.scad"
    assert any("suffix" in p.message for p in core.validate(doc, SHEET))


def test_a_pass_through_script_feeding_another_node_is_refused():
    doc = wrapper_doc()
    doc["nodes"].append({"id": "again", "type": "fold", "inputs": {"creases": "body"}})
    messages = " | ".join(p.message for p in core.validate(doc, SHEET))
    assert "may feed only 'outputs'" in messages


def test_wrapper_is_not_transpiled_and_embedded_scripts_wait_for_the_pack():
    with pytest.raises(GraphCoreError) as exc:
        core.transpile(wrapper_doc(), SHEET)
    assert exc.value.code == "wrapper"
    doc = wrapper_doc()
    doc["nodes"][0]["params"]["part"] = "card"
    doc["nodes"][0]["params"]["output"] = "folded"
    doc["nodes"].append({"id": "blank", "type": "sheet"})
    doc["outputs"] = {"card": "body", "sleeve": "blank"}
    assert core.wrapper_plan(doc, SHEET) is None
    with pytest.raises(GraphCoreError) as exc:
        core.transpile(doc, SHEET)
    assert exc.value.code == "script-node"


# ── The schema ─────────────────────────────────────────────────────────────────


def _commons_graphs():
    for root in (FIXTURES / "graph-core" / "solid-commons",
                 FIXTURES / "assembly-golden" / "commons"):
        yield from sorted(root.glob("*/*.graph.json"))


def test_schema_accepts_every_commons_graph_and_the_wrapper_fixtures():
    validator = jsonschema.Draft7Validator(SCHEMA)
    graphs = list(_commons_graphs()) + sorted((FIXTURES / "y4d").glob("graph-*/*.graph.json"))
    assert len(graphs) >= 18
    for graph in graphs:
        errors = list(validator.iter_errors(json.loads(graph.read_text())))
        assert not errors, (graph, errors[0].message)
    for doc in (declared_doc(), wrapper_doc()):
        assert not list(validator.iter_errors(doc))


def test_schema_refuses_what_the_format_forbids():
    validator = jsonschema.Draft7Validator(SCHEMA)
    bad_old = sheet_doc(version="1.1.0")  # core keys on a 1.1 document
    bad_kernel = sheet_doc()
    del bad_kernel["kernel"]
    bad_script = wrapper_doc()
    bad_script["nodes"][0]["params"]["source"] = "../x.py"
    for doc in (bad_old, bad_kernel, bad_script):
        assert list(validator.iter_errors(doc)), doc


def test_schema_constants_match_the_code():
    assert SCHEMA["properties"]["kernel"]["enum"] == list(core.KERNELS)
    allowed = set(SCHEMA["allOf"][0]["else"]["propertyNames"]["enum"])
    assert allowed == set(core.PACK_KEYS | core.CORE_KEYS)
    assert set(SCHEMA["$defs"]["declarations"]["properties"]) == set(core.DECLARATION_KEYS)
    assert set(SCHEMA["$defs"]["scriptParams"]["properties"]) == {
        "source", "language", "output", "bind", "part"}


def test_every_commons_graph_is_valid_under_the_core():
    for graph in _commons_graphs():
        manifest = json.loads((graph.parent / "project.json").read_text())
        doc = json.loads(graph.read_text())
        assert core.validate(doc, SOLID_PACK, parameters=manifest["parameters"]) == [], graph


@pytest.mark.parametrize("mutate, engine_refuses", [
    (lambda d: d["nodes"].append(copy.deepcopy(d["nodes"][0])), "duplicate node id"),
    (lambda d: d["nodes"][-1].update(type="warp"), "unknown node type"),
    (lambda d: d["outputs"].update(x="missing"), "unknown node"),
    (lambda d: d.update(version="2.0.0"), "'version' must match"),
    (lambda d: d.update(units="in"), "only 'mm'"),
    (lambda d: d.update(extra=1), "unknown top-level keys"),
])
def test_core_refuses_what_the_engine_refuses(mutate, engine_refuses):
    graph = FIXTURES / "graph-core" / "solid-commons" / "flange-plate" / "flange.graph.json"
    manifest = json.loads((graph.parent / "project.json").read_text())
    doc = json.loads(graph.read_text())
    mutate(doc)
    with pytest.raises(ge.GraphError, match=engine_refuses):
        ge.transpile(doc, ge.extract_bindings(manifest["parameters"]))
    assert core.validate(doc, SOLID_PACK, parameters=manifest["parameters"])


# ── Vendorability ──────────────────────────────────────────────────────────────


def test_the_core_imports_only_the_stdlib_and_itself():
    """A kernel vendors the directory and nothing else, so nothing else may be imported."""
    import ast
    import sys

    allowed = set(sys.stdlib_module_names)
    for module in sorted(Path(core.__file__).parent.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] in allowed, (module.name, name)


def test_the_core_lock_is_current():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "scripts" / "qa" / "check_graph_core_lock.py"
    run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


# ── Review fixes ───────────────────────────────────────────────────────────────


def test_the_validator_never_raises_on_a_malformed_document():
    """Every field of four documents swapped for each JSON type: a list of problems,
    never an exception (a crash here stops a whole `y4d-spec check`)."""
    graph = FIXTURES / "graph-core" / "solid-commons" / "idler-608" / "idler.graph.json"
    wrapper = FIXTURES / "y4d" / "graph-wrapper" / "block.graph.json"
    cases = [(wrapper_doc(), SHEET), (declared_doc(), SHEET),
             (json.loads(wrapper.read_text()), SOLID_PACK),
             (json.loads(graph.read_text()), SOLID_PACK)]

    def paths(value, prefix=()):
        yield prefix
        children = value.items() if isinstance(value, dict) else enumerate(value) \
            if isinstance(value, list) else ()
        for key, child in children:
            yield from paths(child, prefix + (key,))

    swapped = 0
    for doc, pack in cases:
        for path in list(paths(doc))[1:]:
            for value in (None, 1, "x", [], {}, [1], {"a": 1}, True):
                mutated = copy.deepcopy(doc)
                target = mutated
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                assert isinstance(core.validate(mutated, pack), list)
                core.label_keys(mutated)
                core.i18n_gaps(mutated)
                core.manifest_projection(mutated)
                swapped += 1
    assert swapped > 1000


def test_a_newer_format_is_refused():
    assert "version" in codes(core.validate(sheet_doc(version="1.3.0"), SHEET))


def test_a_script_node_the_pack_cannot_lower_is_a_problem_not_a_pass():
    doc = wrapper_doc()
    doc["nodes"][0]["params"]["part"] = "card"
    doc["outputs"] = {"card": "body"}
    messages = [p.message for p in core.validate(doc, SHEET)]
    assert any("only as a pure wrapper" in m for m in messages)
    lowering = SheetPack()
    lowering.embedded_scripts = True
    assert core.validate(doc, lowering) == []


def test_visible_when_is_a_checked_expression():
    doc = declared_doc()
    doc["declarations"]["parameters"][1]["visible_when"] = {"expr": "width > 100"}
    assert core.validate(doc, SHEET) == []
    doc["declarations"]["parameters"][1]["visible_when"] = "height > 1"
    assert any("visible_when" in p.where for p in core.validate(doc, SHEET))
    doc["declarations"]["parameters"][1]["visible_when"] = "max(width, 1)"
    assert "expression" in codes(core.validate(doc, SHEET))


# ── P1 pre-check fixes (core 1.0.1) ────────────────────────────────────────────


def test_a_declared_part_parameter_is_wired_and_presets_may_set_it():
    """Six solid cartridges declare `target_part` as a part picker, and presets set it.
    The script node passes it through by contract and may not bind it, so it is wired."""
    doc = wrapper_doc()
    doc["declarations"]["parameters"].append({
        "id": "target_part", "type": "select", "default": "card", "label": {"en": "Part"},
        "options": [{"value": "card", "label": {"en": "Card"}}],
    })
    doc["declarations"]["presets"].append(
        {"id": "sleeve", "label": {"en": "Sleeve"}, "values": {"target_part": "sleeve"}})
    assert core.validate(doc, SHEET) == []
    # A preset may set the part parameter even when the graph does not declare it.
    undeclared = wrapper_doc()
    undeclared["declarations"]["presets"].append(
        {"id": "sleeve", "label": {"en": "Sleeve"}, "values": {"target_part": "sleeve"}})
    assert core.validate(undeclared, SHEET) == []
    # ...but it is still never a script binding.
    bound = wrapper_doc(target_part={"param": "width"})
    assert any("part parameter" in p.message for p in core.validate(bound, SHEET))


def test_a_pure_wrapper_ignores_bindings_meant_for_another_graph():
    """A cartridge with a native graph mode beside script modes binds its parameters
    into the native graph's nodes; the wrapper copies those parameters byte-equal."""
    doc = wrapper_doc()
    doc["declarations"]["parameters"][1]["binding"] = ["native_plate.w", "native_lid.w"]
    assert core.validate(doc, SHEET) == []
    # A native 1.2 graph still resolves its own bindings: a missing node is dangling.
    native = declared_doc()
    native["declarations"]["parameters"][1]["binding"] = "ghost.w"
    assert "dangling-ref" in codes(core.validate(native, SHEET))
