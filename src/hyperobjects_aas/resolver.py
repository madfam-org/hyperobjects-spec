"""Resolve assembly components from projected AAS type environments (ASM-1 §6).

The asset-shells service holds cartridges as stored type shells, not as commons
directories. ``EnvironmentCartridgeResolver`` reads back what the solid projection wrote —
``ParametricModel`` (parameters, defaults, ranges, options), ``GeometryProvision`` (each
mode's parts) and ``MatingInterfaces`` (frames, ``let``, size keys, polarity, symmetry) —
into the manifest shape the keystone helpers take, then resolves exactly like
``CommonsManifestResolver``: same parameter checks (never clamped), same frame evaluation,
same GOC-1 ``instance_id`` over the shell's ``tree_sha256``. For every component the
projection carries faithfully, the two resolvers give the same identity and interfaces, so
the same assembly digest; ``tests/test_assembly_aas.py`` proves it on assemblies A and B.

Which revision of a cartridge a component means is not in the assembly document (it names
a slug); it is in the assembly environment's ``BillOfMaterials`` (``DerivedFrom`` on each
cartridge node, see ``hyperobjects_aas.assembly.component_type_shells``). The resolver is
built with that ``{component id: type shell id}`` map and a ``fetch(shell_id)`` that
returns ``(shell, {submodel idShort: submodel})`` or None. Those ids are versioned
(``…/aas/solid/{slug}/{tree16}/p{N}``, SEM-1 §1); the resolver reads whichever projection
version the BoM names. A service that re-projects the assembly with its own keystone names
the type shells of *its* version, so an assembly published against another projection
version fails the byte-equality check there (ASM-1 §6) rather than here.

    resolver = CompositeResolver(
        cartridge=EnvironmentCartridgeResolver(component_type_shells(env), fetch),
        standard=StandardPartsResolver(bundled_standard_parts_dir()))
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from y4d_spec.assembly import (
    ResolutionError,
    ResolvedComponent,
    cartridge_identity,
    goc1_variables,
    parameter_value_problems,
    resolve_interfaces,
)
from y4d_spec.frame_eval import resolve_parameters

from .ids import parse_shell_id

__all__ = [
    "EnvironmentCartridgeResolver",
    "Fetch",
    "bundled_standard_parts_dir",
    "manifest_from_submodels",
    "requirements_from_submodel",
]

#: ``fetch(type shell id) -> (shell, {submodel idShort: submodel}) | None``
Fetch = Callable[[str], "tuple[Mapping, Mapping[str, Mapping]] | None"]

_INTEGRAL = re.compile(r"^-?[0-9]+$")


def bundled_standard_parts_dir() -> str:
    """The standard-parts catalog shipped in this keystone (``hyperobjects_standard_parts``)."""
    from importlib import resources

    return str(resources.files("hyperobjects_standard_parts").joinpath("parts"))


# ── reading elements back ─────────────────────────────────────────────────────
def _children(element: Mapping) -> list[Mapping]:
    if "submodelElements" in element:
        value = element.get("submodelElements")
    elif element.get("modelType") == "Entity":
        value = element.get("statements")
    else:
        value = element.get("value")
    return [c for c in value if isinstance(c, Mapping)] if isinstance(value, list) else []


def _child(element: Mapping | None, id_short: str) -> Mapping | None:
    if element is None:
        return None
    return next((c for c in _children(element) if c.get("idShort") == id_short), None)


def _typed(value_type: object, lexical: object) -> object:
    """The JSON value a Property's (valueType, value) pair was written from (elements.xsd).

    An ``xs:double`` whose lexical form is integral (``"5"``) was an integer or an
    integral float; both hash identically under GOC-1 canonical JSON, and an int keeps a
    select's ``str(value)`` lookup identical to the manifest's."""
    if not isinstance(lexical, str):
        return None
    if value_type == "xs:boolean":
        return lexical == "true"
    if value_type == "xs:integer":
        return int(lexical)
    if value_type == "xs:double":
        return int(lexical) if _INTEGRAL.match(lexical) else float(lexical)
    return lexical


def _value(element: Mapping | None) -> object:
    if element is None or element.get("modelType") != "Property":
        return None
    return _typed(element.get("valueType"), element.get("value"))


def _list_values(element: Mapping | None) -> list:
    return [_value(c) for c in _children(element)] if element else []


def _parameter(sm_param: Mapping) -> dict | None:
    pid = _value(_child(sm_param, "ParameterId"))
    if not isinstance(pid, str):
        return None
    out: dict = {"id": pid}
    ptype = _value(_child(sm_param, "Type"))
    if ptype is not None:
        out["type"] = ptype
    default = _child(sm_param, "DefaultAsWritten") or _child(sm_param, "Default")
    if default is not None:
        out["default"] = _value(default)
    rng = _child(sm_param, "Range")
    if rng is not None and rng.get("modelType") == "Range":
        out["min"] = _typed(rng.get("valueType"), rng.get("min"))
        out["max"] = _typed(rng.get("valueType"), rng.get("max"))
    step = _child(sm_param, "Step")
    if step is not None:
        out["step"] = _value(step)
    options = _child(sm_param, "Options")
    if options is not None:
        out["options"] = [{"value": _value(_child(o, "Value"))} for o in _children(options)]
    return out


def _vector(element: Mapping | None) -> list | None:
    if element is None:
        return None
    if element.get("modelType") == "SubmodelElementList":
        return _list_values(element)
    return None


def _frame(element: Mapping | None) -> dict | None:
    if element is None:
        return None
    frame: dict = {}
    part = _value(_child(element, "Part"))
    if part is not None:
        frame["part"] = part
    for key, short in (("origin", "Origin"), ("normal", "Normal"), ("x_axis", "XAxis")):
        vec = _vector(_child(element, short))
        if vec is not None:
            frame[key] = vec
    return frame


def _let(element: Mapping | None) -> dict | None:
    if element is None:
        return None
    out: dict = {}
    for entry in _children(element):
        name = _value(_child(entry, "Name"))
        if not isinstance(name, str):
            continue
        expr = _child(entry, "Expression")
        if expr is not None:
            out[name] = _value(expr)
            continue
        out[name] = {
            "param": _value(_child(entry, "LookupParameter")),
            "map": {
                str(_value(_child(row, "ParameterValue"))): _value(_child(row, "Value"))
                for row in _children(_child(entry, "LookupMap") or {})
            },
        }
    return out


def _interface(element: Mapping) -> dict | None:
    iid = _value(_child(element, "InterfaceId"))
    if not isinstance(iid, str):
        return None
    out: dict = {"id": iid}
    size_key = _child(element, "SizeKey")
    if size_key is not None:
        out["size_key"] = _value(size_key)
    elif _child(element, "SizeKeyParameter") is not None:
        out["size_key"] = {
            "param": _value(_child(element, "SizeKeyParameter")),
            "map": {
                str(_value(_child(row, "ParameterValue"))): _value(_child(row, "SizeKey"))
                for row in _children(_child(element, "SizeKeyMap") or {})
            },
        }
    for key, short in (("polarity", "Polarity"), ("symmetry", "Symmetry"),
                       ("geometry_type", "GeometryType")):
        value = _value(_child(element, short))
        if value is not None:
            out[key] = value
    frame = _frame(_child(element, "Frame"))
    if frame is not None:
        out["frame"] = frame
    let = _let(_child(element, "Let"))
    if let is not None:
        out["let"] = let
    return out


def manifest_from_submodels(submodels: Mapping[str, Mapping]) -> dict:
    """The manifest-shaped mapping (``parameters``, ``modes``, ``hyperobject.cdg_interfaces``)
    the solid projection's ``ParametricModel``, ``GeometryProvision`` and
    ``MatingInterfaces`` carry."""
    params = _child(submodels.get("ParametricModel"), "Parameters")
    modes = _child(submodels.get("GeometryProvision"), "Modes")
    interfaces = submodels.get("MatingInterfaces")
    return {
        "parameters": [p for p in (_parameter(c) for c in _children(params or {})) if p],
        "modes": [
            {
                "id": _value(_child(mode, "ModeId")),
                "parts": [_value(_child(part, "PartId"))
                          for part in _children(_child(mode, "Parts") or {})],
            }
            for mode in _children(modes or {})
        ],
        "hyperobject": {
            "cdg_interfaces": [i for i in (_interface(c) for c in _children(interfaces or {}))
                               if i],
        },
    }


def _mlp(element: Mapping | None) -> dict | None:
    if element is None or element.get("modelType") != "MultiLanguageProperty":
        return None
    return {t.get("language"): t.get("text") for t in element.get("value") or []
            if isinstance(t, Mapping)}


def _requirement_block(element: Mapping) -> dict:
    """One ``requirements`` block back from ``solid.requirements_elements``."""
    out: dict = {}
    process = _child(element, "Process")
    if process is not None:
        out["process"] = _list_values(process)
    materials = _child(element, "Materials")
    if materials is not None:
        out["materials"] = {
            key: _list_values(_child(materials, short))
            for key, short in (("any_of", "AnyOf"), ("none_of", "NoneOf"))
            if _child(materials, short) is not None
        }
    bounds = _child(element, "ProcessParameters")
    if bounds is not None:
        params: dict = {}
        for bound in _children(bounds):
            key = _value(_child(bound, "ParameterKey"))
            fields = {f: _value(_child(bound, short)) for f, short in (
                ("min", "Min"), ("max", "Max"), ("value", "Value"), ("unit", "Unit"))
                if _child(bound, short) is not None}
            if set(fields) == {"value"} and not any(
                    _child(bound, s) is not None for s in ("Min", "Max", "Unit")):
                # A bare scalar bound is written as {ParameterKey, Value} and read back so.
                params[key] = fields["value"]
            else:
                params[key] = fields
        out["process_parameters"] = params
    rationale = _mlp(_child(element, "Rationale"))
    if rationale is not None:
        out["rationale"] = rationale
    parts = _child(element, "Parts")
    if parts is not None:
        out["parts"] = {_value(_child(p, "PartId")): _requirement_block(p)
                        for p in _children(parts)}
        for block in out["parts"].values():
            block.pop("parts", None)
    return out


def requirements_from_submodel(submodel: Mapping | None) -> dict | None:
    """A cartridge's ``requirements`` back from its ``RequirementProfile`` (None if it states
    none). Re-projecting the result reproduces the submodel's requirement elements, which is
    what makes an assembly's requirement roll-up derivable from stored shells too."""
    if submodel is None:
        return None
    block = _requirement_block(submodel)
    return block or None


def _specific(shell: Mapping) -> dict[str, str]:
    info = shell.get("assetInformation") or {}
    return {s.get("name"): s.get("value") for s in info.get("specificAssetIds") or []
            if isinstance(s, Mapping)}


class EnvironmentCartridgeResolver:
    """Cartridge components resolved from stored solid type shells (see module doc)."""

    def __init__(self, shells: Mapping[str, str], fetch: Fetch):
        self.shells = dict(shells)
        self.fetch = fetch

    def resolve(self, component: Mapping) -> ResolvedComponent:
        source = component.get("source") if isinstance(component.get("source"), Mapping) else {}
        commons, slug = source.get("commons"), source.get("slug")
        cid = component.get("id")
        if commons != "solid":
            raise ResolutionError([f"commons {commons!r} is not served here (solid only)"])
        shell_id = self.shells.get(cid)
        if shell_id is None:
            raise ResolutionError([
                f"no type shell is named for cartridge component '{cid}' (its BillOfMaterials "
                "node carries no DerivedFrom reference)"])
        parts = parse_shell_id(shell_id)
        if parts is None or parts.kind != "solid" or parts.slug != slug:
            raise ResolutionError([
                f"type shell {shell_id!r} is not a revision of the solid cartridge {slug!r} "
                f"(…/aas/solid/{slug}/{{tree16}}/p{{N}})"])
        fetched = self.fetch(shell_id)
        if fetched is None:
            raise ResolutionError([f"type shell {shell_id!r} is not published"])
        shell, submodels = fetched
        tree = _specific(shell).get("tree_sha256")
        if not isinstance(tree, str) or not tree.startswith(parts.revision16):
            raise ResolutionError([f"type shell {shell_id!r} carries no matching tree_sha256"])
        manifest = manifest_from_submodels(submodels)
        mode_id, part = source.get("mode"), source.get("part")
        given = source.get("parameters") or {}
        modes = {m["id"]: m for m in manifest["modes"] if isinstance(m.get("id"), str)}
        problems: list[str] = []
        produced: list[str] = []
        if mode_id not in modes:
            problems.append(
                f"cartridge '{slug}' has no mode {mode_id!r} "
                f"(modes: {', '.join(sorted(modes)) or 'none'})")
        else:
            produced = [p for p in modes[mode_id]["parts"] if isinstance(p, str)]
            if not produced:
                problems.append(
                    f"cartridge '{slug}' mode '{mode_id}' lists no parts in GeometryProvision; "
                    "the parts it produces cannot be read back from the shell")
            elif part is not None and part not in produced:
                problems.append(
                    f"cartridge '{slug}' mode '{mode_id}' does not produce part {part!r} "
                    f"(it produces: {', '.join(produced)})")
        problems.extend(f"cartridge '{slug}': {p}"
                        for p in parameter_value_problems(manifest["parameters"], given))
        if problems:
            raise ResolutionError(problems)
        values = resolve_parameters(manifest, given)
        identity, details = cartridge_identity(
            slug=slug, mode=mode_id, part=part, tree_sha256=tree,
            variables=goc1_variables(manifest["parameters"], values))
        available = [part] if part is not None else produced
        return ResolvedComponent(
            component_id=cid,
            source_type="cartridge",
            label=f"{commons}/{slug}:{mode_id}" + (f"/{part}" if part else ""),
            identity=identity,
            interfaces=resolve_interfaces(manifest, given, available_parts=available),
            details={
                **details,
                "parts": list(available),
                "type_shell": shell_id,
                **({"requirements": req} if (req := requirements_from_submodel(
                    submodels.get("RequirementProfile"))) else {}),
            },
        )
