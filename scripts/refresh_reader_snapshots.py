#!/usr/bin/env python3
"""Re-vendor the two commons catalogs and the bridge graph for the cross-commons reader.

RFC 0039 G4 is "one lexicon, both encyclopaedias, the bridge graph as navigation", and
the reader that renders it must build **hermetically** — no network, no platform
checkout, deterministic output. That means the two catalogs and the bridge graph are
vendored here and pinned to a commit, exactly the way ``commons-slugs.snapshot.json``
pins the slug sets for the lexicon lane.

    python3 scripts/refresh_reader_snapshots.py \\
        --yantra4d ../yantra4d --fashion-cabinet ../fashion-cabinet

**What is vendored, and what is deliberately not.** Each entry carries the *catalog
metadata* the commons already publishes about it — names, taxonomy, licence, interface
declarations, piece and parameter counts, and the short blurb the published catalog or
material card attaches. It does NOT carry article prose. RFC 0039 §2 makes the
per-cartridge ``docs/README.md`` single-source with no parallel corpus, so copying a
README body into this repo is the one thing the reader must not do: every entry page
links to the manifest and to the object's page on its own commons instead.

**Why it reads through ``git show`` rather than the working tree.** Its sibling
``refresh_catalog_snapshot.py`` reads a checkout's files and records
``git rev-parse HEAD``. This one names the ref explicitly (``--ref``, default
``origin/main``) and reads every file out of that commit, so the snapshot records the
commit it was actually built from even when the checkout is sitting on some other
branch — and so refreshing never needs a checkout to be moved. The recorded sha is the
full one: a reader comparing two snapshots should not have to guess at an abbreviation.

Sources, per commons:

* yantra4d — ``docs/commons-catalog.json`` (500 cartridges) plus
  ``materials/*/material.json`` (the cards no catalog publishes).
* fashion-cabinet — ``docs/commons-catalog.json`` (516 objects) plus its
  ``materials/*/material.json``, and the bridge graph:
  ``docs/interfaces/yantra4d-consumers.json`` (the published back-edge) and
  ``docs/interfaces/bridge-index.json`` (whose ``unlinked_claims`` carry the reason an
  honest claim does not resolve).

The bridge snapshot keeps BOTH directions rather than deriving one from the other. They
come from two different published files, and whether they agree is a fact worth being
able to check rather than one to assume — ``fc-spec reader`` reports the agreement.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

CATALOG_DIR = (
    Path(__file__).resolve().parent.parent / "src/hyperobjects_lexicon/catalogs"
)

REPO_URL = {
    "yantra4d": "https://github.com/madfam-org/yantra4d",
    "fashion-cabinet": "https://github.com/madfam-org/fashion-cabinet",
}

CATALOG_COMMENT = (
    "A vendored, pinned slice of the {repo} commons catalog, reduced to what the "
    "cross-commons reader (RFC 0039 G4) renders. Catalog METADATA only — names, "
    "taxonomy, licence, interfaces, counts, and the short blurb the published catalog "
    "or material card carries. No article prose: RFC 0039 §2 keeps each cartridge's "
    "docs/README.md single-source in its own commons, and the reader links to it "
    "rather than copying it. Refresh with scripts/refresh_reader_snapshots.py."
)

BRIDGE_COMMENT = (
    "The cross-commons bridge graph, vendored and pinned: Fashion Cabinet garments to "
    "Yantra4D hardware through hardware_ref (the forward claims), and Yantra4D hardware "
    "to its Fashion Cabinet consumers through the back-edge fashion-cabinet publishes "
    "for yantra4d to vendor. Both directions are kept because they come from two "
    "different published files; whether they agree is checked, not assumed. "
    "unlinked_claims is fashion-cabinet's own report of the claims that do not resolve, "
    "carried verbatim — the reader reports them and never fails on them, matching the "
    "back-edge convention. Refresh with scripts/refresh_reader_snapshots.py."
)


def _run(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def _commit(repo: Path, ref: str) -> str:
    return _run(repo, "rev-parse", ref).strip()


def _show_json(repo: Path, ref: str, path: str) -> object:
    return json.loads(_run(repo, "show", f"{ref}:{path}"))


def _list_materials(repo: Path, ref: str) -> list[str]:
    """Material-card slugs at ``materials/<slug>/material.json`` in that commit."""
    try:
        listing = _run(repo, "ls-tree", "-r", "--name-only", ref, "materials/")
    except subprocess.CalledProcessError:
        return []
    out = []
    for line in listing.splitlines():
        parts = line.split("/")
        if len(parts) == 3 and parts[0] == "materials" and parts[2] == "material.json":
            out.append(parts[1])
    return sorted(out)


def _texts(block: object) -> dict[str, str]:
    """A multilingual block reduced to the languages actually present and non-empty.

    This is where the reader's honesty about language starts: an empty string is not a
    language the entry has, and a facet dropped here is a facet the reader will never
    offer a switcher for.
    """
    if not isinstance(block, dict):
        return {}
    return {
        lang: value.strip()
        for lang, value in sorted(block.items())
        if isinstance(value, str) and value.strip()
    }


def _facts(pairs: list[tuple[str, object]]) -> list[list[str]]:
    """Ordered label/value pairs, skipping anything absent. A list (not a dict) so the
    render order is the capture order and cannot depend on hash iteration."""
    out = []
    for key, value in pairs:
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = "yes" if value else "no"
        out.append([key, str(value)])
    return out


def _y4d_entries(repo: Path, ref: str) -> list[dict]:
    catalog = _show_json(repo, ref, "docs/commons-catalog.json")
    entries = []
    for cart in catalog["cartridges"]:
        entries.append(
            {
                "slug": cart["slug"],
                "kind": "cartridge",
                "names": {"en": cart["name"]} if cart.get("name") else {},
                "summary": _texts(cart.get("societal_benefit")),
                "summary_label": "societal_benefit",
                "group": cart.get("domain") or "uncategorized",
                "license": cart.get("commons_license"),
                "facts": _facts(
                    [
                        ("domain", cart.get("domain")),
                        ("engines", cart.get("engines")),
                        ("dual engine", cart.get("dual_engine")),
                        ("modes", cart.get("modes")),
                        ("parts", cart.get("parts")),
                        ("parameters", cart.get("parameters")),
                        ("export formats", cart.get("export_formats")),
                    ]
                ),
                "interfaces": [
                    {
                        "id": iface.get("id"),
                        "type": iface.get("geometry_type"),
                        "label": iface.get("label"),
                        "standard": iface.get("standard"),
                    }
                    for iface in cart.get("cdg_interfaces") or []
                ],
                "standards": sorted(cart.get("standards") or []),
                "manifest": (cart.get("source") or {}).get("manifest"),
            }
        )
    for slug in _list_materials(repo, ref):
        card = _show_json(repo, ref, f"materials/{slug}/material.json")
        head = card.get("material") or {}
        entries.append(
            {
                "slug": slug,
                "kind": "material",
                "names": (
                    {"en": head["name"]}
                    if isinstance(head.get("name"), str)
                    else _texts(head.get("name"))
                ),
                "summary": {},
                "summary_label": None,
                "group": head.get("category") or "material",
                "license": None,
                "facts": _facts(
                    [
                        ("category", head.get("category")),
                        ("AM technology", head.get("am_technology")),
                        ("vendor", head.get("vendor")),
                    ]
                ),
                "interfaces": [],
                "standards": [],
                "manifest": f"materials/{slug}/material.json",
            }
        )
    return sorted(entries, key=lambda e: e["slug"])


def _fc_entries(repo: Path, ref: str) -> list[dict]:
    catalog = _show_json(repo, ref, "docs/commons-catalog.json")
    entries = []
    for obj in catalog["objects"]:
        licenses = obj.get("licenses") or {}
        entries.append(
            {
                "slug": obj["slug"],
                "kind": "cartridge",
                "names": _texts(obj.get("names")),
                "summary": {},
                "summary_label": None,
                "group": obj.get("band") or "unranked",
                "license": licenses.get("commons") or licenses.get("attribution"),
                "facts": _facts(
                    [
                        ("kind", obj.get("kind")),
                        ("band", obj.get("band")),
                        ("rank", obj.get("rank")),
                        ("family", obj.get("family")),
                        ("domain", obj.get("domain")),
                        ("pieces", obj.get("pieces")),
                        ("parameters", obj.get("parameters")),
                        ("fabrics", obj.get("fabrics")),
                        ("export formats", obj.get("export_formats")),
                    ]
                ),
                "interfaces": [
                    {
                        "id": iface.get("id"),
                        "type": iface.get("type"),
                        "label": None,
                        "standard": None,
                    }
                    for iface in obj.get("interfaces") or []
                ],
                "standards": [],
                "manifest": (obj.get("source") or {}).get("manifest"),
            }
        )
    for slug in _list_materials(repo, ref):
        card = _show_json(repo, ref, f"materials/{slug}/material.json")
        fabric = card.get("fabric") or {}
        physical = card.get("physical") or {}
        entries.append(
            {
                "slug": slug,
                "kind": "material",
                "names": _texts(fabric.get("name")),
                "summary": _texts((card.get("compensations") or {}).get("notes")),
                "summary_label": "compensation_notes",
                "group": fabric.get("class") or "material",
                "license": None,
                "facts": _facts(
                    [
                        ("class", fabric.get("class")),
                        ("weave", fabric.get("weave")),
                        ("gsm", physical.get("gsm")),
                        ("width (mm)", physical.get("width_mm")),
                        ("drape class", physical.get("drape_class")),
                    ]
                ),
                "interfaces": [],
                "standards": [],
                "manifest": f"materials/{slug}/material.json",
            }
        )
    return sorted(entries, key=lambda e: e["slug"])


def _bridges(fc_repo: Path, fc_ref: str, fc_catalog: object) -> dict:
    consumers = _show_json(fc_repo, fc_ref, "docs/interfaces/yantra4d-consumers.json")
    index = _show_json(fc_repo, fc_ref, "docs/interfaces/bridge-index.json")

    edges = []
    for obj in fc_catalog["objects"]:
        ref = obj.get("hardware_ref")
        if not ref:
            continue
        edges.append(
            {
                "garment": obj["slug"],
                "platform": ref.get("platform"),
                "hardware": ref.get("project_slug"),
                "linked": bool(ref.get("linked")),
                "params_map_keys": sorted(ref.get("params_map_keys") or []),
            }
        )
    edges.sort(key=lambda e: (e["garment"], e["hardware"] or ""))

    back = []
    for hardware, rows in (consumers.get("consumers") or {}).items():
        for row in rows:
            back.append(
                {
                    "hardware": hardware,
                    "garment": row["slug"],
                    "drives": sorted(row.get("drives") or []),
                    "params_map": dict(sorted((row.get("params_map") or {}).items())),
                }
            )
    back.sort(key=lambda e: (e["hardware"], e["garment"]))

    claims = []
    for claim in index.get("unlinked_claims") or []:
        claims.append(
            {
                "hardware": claim.get("target_slug"),
                "garments": sorted(claim.get("requesting") or []),
                "resolves_in_snapshot": bool(claim.get("resolves_in_snapshot")),
                "reason": claim.get("reason"),
            }
        )
    claims.sort(key=lambda c: c["hardware"] or "")

    return {
        "edges": edges,
        "back_edges": back,
        "unlinked_claims": claims,
        "resolved_against": {
            "yantra4d_commit": (index.get("hardware_snapshot") or {}).get(
                "upstream_commit"
            )
        },
    }


def _write(path: Path, doc: dict) -> int:
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yantra4d", required=True, type=Path, help="path to a yantra4d clone")
    ap.add_argument(
        "--fashion-cabinet", required=True, type=Path, help="path to a fashion-cabinet clone"
    )
    ap.add_argument(
        "--ref",
        default="origin/main",
        help="the git ref to read both repos at (default: origin/main). Read with "
        "`git show <ref>:<path>`, so no checkout is moved and the recorded sha is "
        "exactly what was captured.",
    )
    ap.add_argument(
        "--yantra4d-ref",
        help="read yantra4d at this ref instead of --ref. The two commons move "
        "independently, and a refresh that has to take both at whatever HEAD happens "
        "to be cannot reproduce a snapshot; naming the commit can.",
    )
    ap.add_argument("--fashion-cabinet-ref", help="read fashion-cabinet at this ref instead")
    args = ap.parse_args(argv)
    y4d_ref = args.yantra4d_ref or args.ref
    fc_ref = args.fashion_cabinet_ref or args.ref

    today = datetime.date.today().isoformat()
    try:
        y4d_commit = _commit(args.yantra4d, y4d_ref)
        fc_commit = _commit(args.fashion_cabinet, fc_ref)
        y4d_entries = _y4d_entries(args.yantra4d, y4d_ref)
        fc_catalog = _show_json(args.fashion_cabinet, fc_ref, "docs/commons-catalog.json")
        fc_entries = _fc_entries(args.fashion_cabinet, fc_ref)
        bridges = _bridges(args.fashion_cabinet, fc_ref, fc_catalog)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print(
            f"ERROR: cannot read the commons (yantra4d@{y4d_ref}, "
            f"fashion-cabinet@{fc_ref}) — {exc}",
            file=sys.stderr,
        )
        return 2

    # Read-proof, the same guard the slug snapshot keeps: an empty side would make every
    # page on that side vanish while the build still reported success.
    if not y4d_entries or not fc_entries or not bridges["edges"]:
        print(
            f"ERROR: empty capture (yantra4d={len(y4d_entries)} "
            f"fashion-cabinet={len(fc_entries)} edges={len(bridges['edges'])})",
            file=sys.stderr,
        )
        return 2

    written = []
    for repo, entries, commit, ref, paths in (
        (
            "yantra4d",
            y4d_entries,
            y4d_commit,
            y4d_ref,
            ["docs/commons-catalog.json", "materials/*/material.json"],
        ),
        (
            "fashion-cabinet",
            fc_entries,
            fc_commit,
            fc_ref,
            ["docs/commons-catalog.json", "materials/*/material.json"],
        ),
    ):
        doc = {
            "schema_version": 1,
            "_comment": CATALOG_COMMENT.format(repo=repo),
            "captured_at": today,
            "source": {
                "repo": repo,
                "url": REPO_URL[repo],
                "ref": ref,
                "commit": commit,
                "paths": paths,
                "entries": len(entries),
                "cartridges": sum(1 for e in entries if e["kind"] == "cartridge"),
                "materials": sum(1 for e in entries if e["kind"] == "material"),
            },
            "entries": entries,
        }
        size = _write(CATALOG_DIR / f"{repo}-catalog.snapshot.json", doc)
        written.append(f"{repo}: {len(entries)} entries ({size // 1024} KiB)")

    bridge_doc = {
        "schema_version": 1,
        "_comment": BRIDGE_COMMENT,
        "captured_at": today,
        "sources": {
            "fashion-cabinet": {
                "url": REPO_URL["fashion-cabinet"],
                "ref": fc_ref,
                "commit": fc_commit,
                "paths": [
                    "docs/commons-catalog.json",
                    "docs/interfaces/yantra4d-consumers.json",
                    "docs/interfaces/bridge-index.json",
                ],
            },
            "yantra4d": {
                "url": REPO_URL["yantra4d"],
                "ref": y4d_ref,
                "commit": y4d_commit,
                "paths": ["docs/commons-catalog.json"],
            },
        },
        "resolved_against": bridges["resolved_against"],
        "counts": {
            "edges": len(bridges["edges"]),
            "back_edges": len(bridges["back_edges"]),
            "unlinked_claims": len(bridges["unlinked_claims"]),
        },
        "edges": bridges["edges"],
        "back_edges": bridges["back_edges"],
        "unlinked_claims": bridges["unlinked_claims"],
    }
    size = _write(CATALOG_DIR / "commons-bridges.snapshot.json", bridge_doc)
    written.append(
        f"bridges: {len(bridges['edges'])} forward + {len(bridges['back_edges'])} back "
        f"+ {len(bridges['unlinked_claims'])} unlinked claims ({size // 1024} KiB)"
    )

    print(
        f"refreshed: yantra4d {y4d_ref} {y4d_commit[:9]}, "
        f"fashion-cabinet {fc_ref} {fc_commit[:9]}"
    )
    for line in written:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
