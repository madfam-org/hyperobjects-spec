"""Tests for the cross-commons reader (RFC 0039 G4).

The reader makes four promises that a human cannot check by looking at 1189 pages, so
each one is a test here instead:

1. **A rebuild is byte-identical**, and the committed tree matches it. Without that,
   `--check` is decoration.
2. **Every bridge edge either resolves to a page on both ends, or is reported as
   unresolved** — reported, never fatal, matching the back-edge convention.
3. **No page offers a language the entry does not have.** The switcher is built from the
   data, and this is what holds it there when the data changes.
4. **Every count in the docs is script-emitted.** A number typed by hand is a number
   that will be wrong after the next wave.

Plus the structural bars the reader claims and a reader cannot verify by eye: no
JavaScript, no external asset, no dead internal link, and no article prose vendored.
"""

import json
import re
from pathlib import Path

import pytest

from hyperobjects_lexicon.lexicon import LANGUAGES
from hyperobjects_lexicon.reader import (
    READER_DIR,
    REPOS,
    build,
    check,
    load_model,
    reader_counts,
    render,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = REPO_ROOT / READER_DIR

LANG_NAV = re.compile(r'<nav class="langs"[^>]*data-langs="([^"]*)"(.*?)</nav>', re.DOTALL)
LANG_LINK = re.compile(r'<a href="#([a-z]{2})"')
LANG_SECTION = re.compile(r'<section class="lang" id="([a-z]{2})" lang="([a-z]{2})">')
HREF = re.compile(r'href="([^"]+)"')


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def files(model):
    return render(model)


# ── 1. determinism, and the committed tree ───────────────────────────────────


def test_render_is_deterministic(model):
    """Same inputs, byte-identical output. Two renders, not one compared with itself:
    a dict comprehension over an unsorted set would pass the second and fail this."""
    assert render(model) == render(model)


def test_a_fresh_build_reproduces_the_committed_tree(tmp_path, model):
    build(tmp_path / "reader", model)
    assert check(tmp_path / "reader", model) == []


def test_the_committed_reader_matches_a_rebuild(model):
    """The one that matters: what is in the repo IS what the build produces."""
    problems = check(COMMITTED, model)
    assert problems == [], f"docs/reader is stale — {problems[:5]}"


def test_check_fails_on_a_missing_directory(tmp_path, model):
    assert check(tmp_path / "nothing-here", model)


def test_check_fails_on_a_deleted_page(tmp_path, model):
    build(tmp_path / "reader", model)
    (tmp_path / "reader" / "index.html").unlink()
    assert any(p.startswith("missing: index.html") for p in check(tmp_path / "reader", model))


def test_check_fails_on_an_extra_page(tmp_path, model):
    build(tmp_path / "reader", model)
    (tmp_path / "reader" / "stowaway.html").write_text("<p>hi</p>", encoding="utf-8")
    assert any(p.startswith("unexpected: stowaway.html") for p in check(tmp_path / "reader", model))


def test_check_fails_on_one_changed_byte(tmp_path, model):
    build(tmp_path / "reader", model)
    page = tmp_path / "reader" / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert any(p.startswith("stale: index.html") for p in check(tmp_path / "reader", model))


def test_build_removes_a_page_the_build_no_longer_makes(tmp_path, model):
    """A stale page left behind is a page `--check` would have to pass on a lie."""
    dest = tmp_path / "reader"
    build(dest, model)
    (dest / "terms" / "gone.html").write_text("<p>old</p>", encoding="utf-8")
    build(dest, model)
    assert not (dest / "terms" / "gone.html").exists()
    assert check(dest, model) == []


def test_page_count_matches_what_the_summary_claims(files, model):
    counts = reader_counts(model)
    rendered = sum(1 for name in files if name.endswith(".html"))
    assert counts["pages"] == rendered
    summary = json.loads(files["summary.json"])
    assert summary["pages"] == rendered


# ── 2. the bridge graph ──────────────────────────────────────────────────────


def test_every_bridge_edge_resolves_on_both_ends_or_is_reported(files, model):
    """The G4 bar. An edge is either navigable in both directions, or it appears on the
    bridges page as unresolved. Silently dropping one is the failure this forbids."""
    bridges_page = files["bridges.html"]
    for edge in model.edges + model.back_edges:
        if edge.resolved:
            source_repo, source_slug = edge.source.split("/", 1)
            target_repo, target_slug = edge.target.split("/", 1)
            assert f"{source_repo}/{source_slug}.html" in files
            assert f"{target_repo}/{target_slug}.html" in files
            # and the page actually carries the link, in the direction the edge runs
            page = files[f"{source_repo}/{source_slug}.html"]
            assert f"../{target_repo}/{target_slug}.html" in page, (
                f"{edge.source} does not link to {edge.target}"
            )
        else:
            assert edge.target in bridges_page or edge.source in bridges_page, (
                f"unresolved edge {edge.source} → {edge.target} is not reported"
            )


def test_the_unresolved_edge_the_commons_actually_has_is_reported(files, model):
    """Calibration against the real data: fashion-cabinet publishes exactly one claim
    that resolves against no yantra4d cartridge, and it must be visible, with its
    reason, rather than quietly absent."""
    unresolved = [e for e in model.edges if not e.resolved]
    assert unresolved, "the fixture data no longer exercises the unresolved path"
    for edge in unresolved:
        assert edge.target in files["bridges.html"]
        assert edge.target in files[f"{edge.source.split('/')[0]}/{edge.source.split('/')[1]}.html"]
    assert "Sin resolver" in files["bridges.html"]


def test_unresolved_is_reported_and_never_fatal():
    """The yantra4d back-edge convention, as an exit code: a build over data carrying an
    unresolved cross-commons claim still succeeds."""
    from hyperobjects_lexicon.cli import run_reader

    class _Args:
        out = str(COMMITTED)
        check = True
        status = False

    assert reader_counts()["bridges"]["unresolved"] > 0
    assert run_reader(_Args(), "fc-spec") == 0


def test_the_two_bridge_directions_agree(model):
    """The forward claims and the published back edge come from two different files.
    That they describe the same 299 relationships is checked, not assumed."""
    counts = reader_counts(model)["bridges"]
    assert counts["mirrored"] == counts["linked"] == counts["back_edges"]


def test_back_edge_provenance_is_stated_when_it_differs(files, model):
    """fashion-cabinet resolved its back edge against one yantra4d commit; this repo
    pins another. The reader must say so rather than implying a single commit."""
    against = reader_counts(model)["bridges"]["resolved_against"]
    pinned = model.catalogs["yantra4d"]["source"]["commit"]
    assert against in files["bridges.html"]
    assert pinned in files["bridges.html"]
    if against != pinned:
        assert "distinto del catálogo fijado" in files["bridges.html"]


# ── 3. language honesty ──────────────────────────────────────────────────────


def _offered(page: str) -> set[str]:
    """The languages a page's switcher offers, read back out of the markup."""
    match = LANG_NAV.search(page)
    if not match:
        return set()
    declared = set(match.group(1).split())
    linked = set(LANG_LINK.findall(match.group(2)))
    assert declared == linked, "data-langs and the anchors disagree"
    return declared


def _sections(page: str) -> set[str]:
    pairs = LANG_SECTION.findall(page)
    assert all(a == b for a, b in pairs), "a section's id and lang attribute disagree"
    return {a for a, _ in pairs}


def test_no_page_offers_a_language_it_has_no_section_for(files):
    for name, page in sorted(files.items()):
        if not name.endswith(".html"):
            continue
        assert _offered(page) == _sections(page), name


def test_a_term_offers_exactly_the_languages_it_defines(files, model):
    for term_id, doc in sorted(model.terms.items()):
        expected = {
            lang
            for lang in LANGUAGES
            if (doc.get("term") or {}).get(lang) and (doc.get("definition") or {}).get(lang)
        }
        assert _offered(files[f"terms/{term_id}.html"]) == expected, term_id


def test_a_catalog_entry_offers_exactly_the_languages_it_carries(files, model):
    """The debt phase G-L will pay, made visible: yantra4d is English-named with en/es
    blurbs, Fashion Cabinet's names run four languages deep at four different depths,
    and no page may claim more than its own entry has."""
    for key, entry in sorted(model.entries.items()):
        expected = {
            lang
            for lang in LANGUAGES
            if (entry.get("names") or {}).get(lang) or (entry.get("summary") or {}).get(lang)
        }
        repo, slug = key.split("/", 1)
        assert _offered(files[f"{repo}/{slug}.html"]) == expected, key


def test_the_catalogs_really_are_short_of_languages(model):
    """Calibration: if every catalog entry were quadrilingual the test above would be
    vacuous. It is not — and the reader exists partly to keep that visible."""
    counts = reader_counts(model)["catalog"]
    assert counts["yantra4d"]["languages"]["fr"] < counts["yantra4d"]["entries"]
    assert counts["fashion-cabinet"]["languages"]["pt"] < counts["fashion-cabinet"]["entries"]


SECTION_BADGE = re.compile(
    r'<section class="lang" id="([a-z]{2})"[^>]*>\s*<h2>[^<]*</h2>\s*'
    r'<p class="review"><span class="badge[^"]*">([a-z]+)</span>'
)


def test_every_language_section_of_a_term_states_its_own_review_state(files, model):
    """COMMONS_VOCABULARY.md's rule, rendered: a drafting pass must never read as a
    review, in any of the four languages. The state a section shows is the per-language
    facet where the entry declares one and the entry's own state otherwise — never the
    best of the four."""
    generated_seen = 0
    for term_id, doc in sorted(model.terms.items()):
        review = doc.get("review_status")
        review = review if isinstance(review, dict) else {}
        facets = review.get("languages") or {}
        page = files[f"terms/{term_id}.html"]
        shown = dict(SECTION_BADGE.findall(page))
        assert set(shown) == _sections(page), term_id
        for lang, state in sorted(shown.items()):
            assert state == (facets.get(lang) or review.get("state", "unmarked")), (
                f"{term_id}[{lang}]"
            )
            generated_seen += state == "generated"
    assert generated_seen, "no generated term in the corpus — this test proved nothing"


# ── 4. counts, and the structural bars ───────────────────────────────────────


def test_the_counts_in_the_docs_are_script_emitted():
    """`refresh_reader_counts.py --check` is the lane; this is it as a test, so a doc
    that drifts fails the suite and not only CI."""
    import importlib.util

    script = REPO_ROOT / "scripts" / "refresh_reader_counts.py"
    spec = importlib.util.spec_from_file_location("refresh_reader_counts", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0


@pytest.mark.parametrize("relative", ["README.md", "docs/COMMONS_VOCABULARY.md"])
def test_no_stale_corpus_count_anywhere_in_a_document(relative):
    """The counts script owns its delimited blocks; this catches a number typed into the
    prose around them, which is where the last three stale counts actually lived."""
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    counts = reader_counts()
    total = counts["terms"]["total"]
    review = counts["terms"]["review"]

    for found in re.findall(r"terms=(\d+)", text):
        assert int(found) == total, f"{relative}: terms={found}, corpus has {total}"
    for a, b in re.findall(r"(\d+)/(\d+) terms quadrilingual", text):
        assert (int(a), int(b)) == (total, total), relative
    for state in ("reviewed", "generated", "unmarked"):
        for found in re.findall(rf"\b{state}=(\d+)\b", text):
            assert int(found) == review[state], f"{relative}: {state}={found}"
    for a, b in re.findall(r"\*\*(\d+) terms, (\d+) of them", text):
        assert int(a) == total, relative
        assert int(b) == review["generated"], relative


def test_no_javascript_and_no_external_asset(files):
    """"Works with no JavaScript" is only a claim until nothing can smuggle any in."""
    for name, page in sorted(files.items()):
        if not name.endswith(".html"):
            continue
        assert "<script" not in page.lower(), name
        assert not re.search(r'\son[a-z]+\s*=\s*"', page), name
        assert not re.search(r'\ssrc\s*=', page), name
        for href in HREF.findall(page):
            if href.startswith("http"):
                assert "/blob/" in href, f"{name}: unexpected external link {href}"
        assert page.count("<link rel=\"stylesheet\"") == 1, name


def test_every_internal_link_lands_on_a_page(files):
    """1189 pages of cross-links; a dead one would be invisible without this."""
    for name, page in sorted(files.items()):
        if not name.endswith(".html"):
            continue
        base = Path(name).parent
        for href in HREF.findall(page):
            if href.startswith("http") or href.startswith("#"):
                continue
            parts: list[str] = []
            for part in (base / href.split("#", 1)[0]).parts:
                if part == "..":
                    parts.pop()
                else:
                    parts.append(part)
            assert "/".join(parts) in files, f"{name} → {href}"


def test_no_article_prose_is_vendored():
    """RFC 0039 §2: the per-cartridge README is single-source. The snapshots must carry
    catalog metadata and never an article body, and every entry page must link out to
    the manifest at the pinned commit instead."""
    from hyperobjects_lexicon.reader import load_reader_catalog

    forbidden = {"description", "readme", "body", "article", "prose", "docs"}
    for repo in REPOS:
        snapshot = load_reader_catalog(repo)
        for entry in snapshot["entries"]:
            assert forbidden.isdisjoint(entry), f"{repo}/{entry['slug']}"


def test_every_entry_page_links_to_its_pinned_manifest(files, model):
    for key, entry in sorted(model.entries.items()):
        if not entry.get("manifest"):
            continue
        repo, slug = key.split("/", 1)
        commit = model.catalogs[repo]["source"]["commit"]
        page = files[f"{repo}/{slug}.html"]
        assert f"/blob/{commit}/{entry['manifest']}" in page, key


def test_every_embodied_by_reference_has_a_page_or_is_reported(files, model):
    """The lexicon lane resolves `embodied_by` against the slug snapshot; the reader
    resolves it against the catalog snapshots, which are a different capture. Where the
    two disagree the reader reports rather than dropping the reference."""
    for term_id, doc in sorted(model.terms.items()):
        page = files[f"terms/{term_id}.html"]
        for ref in doc.get("embodied_by") or []:
            assert ref in page
    for problem in model.dangling_embodied_by:
        assert problem in files["index.html"]
