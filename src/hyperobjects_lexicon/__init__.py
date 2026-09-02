"""hyperobjects_lexicon — the Commons Lexicon: the shared vocabulary of both commons.

RFC 0039 ruled that the two commons' *terms* live here, in the spec package, while each
commons keeps its own *articles*. The reasoning is the same move this package already
made once: the bar lived inside the repos, and the shared part got extracted. A term is
shared by definition — the case that named the problem is a dialect split, Fashion
Cabinet's ``zipper_tape`` and Yantra4D's ``tape_edge`` being one physical thing under two
spellings. Neither repo can own that entry; both need it.

    from hyperobjects_lexicon import load_lexicon, check_lexicon

    lex = load_lexicon()                 # the bundled corpus, id -> term dict
    lex["tape-edge"]["term"]["pt"]       # 'debrum de fita costurado'

    result = check_lexicon(lex)          # the lane, as a library call
    result.ok, result.problems

On the command line, on either tool a contributor already has installed::

    fc-spec lexicon            # or: y4d-spec lexicon
    fc-spec lexicon --catalog /path/to/commons-catalog.json

Terms are born quadrilingual — en/es/fr/pt, all four required to ship (RFC 0039 §7).
That is a ship gate rather than an aspiration: the four-language rule is only free at
authoring time, and every entry that ships partial becomes a backfill nobody schedules.

Four layers ship here, and they are deliberately distinct:

* ``lexicon`` — the terms. Words, defined in four languages, each pointing at the
  cartridges that embody it and carrying the constraint that comes with it.
* ``vocabulary`` — the controlled vocabularies (G3). KEYS rather than words: the literal
  strings a manifest writes, with the near-duplicates canonicalised and the cross-commons
  equivalences recorded as explicit edges.
* ``articles`` — the frontmatter contract (G2). The encyclopaedia layer's machine-readable
  half, pointing AT each cartridge's README rather than copying it.
* ``reader`` — the cross-commons reader (G4). One static, JavaScript-free surface over
  all of the above plus two pinned catalog snapshots and the pinned bridge graph, so a
  visitor can look a word up and walk it to the objects, and walk a garment to the solid
  it resolves and back. Built by ``<tool> reader`` into ``docs/reader/`` and committed;
  ``--check`` fails closed when the committed tree and a rebuild disagree.

``dictionary`` is how the first three are read: ``define``, ``lookup`` and ``related``, the
RFC 0039 §6.2 tools both platforms' MCP servers wrap.
"""

from __future__ import annotations

from .articles import (
    ArticleResult,
    article_status,
    check_article,
    check_articles,
    language_coverage,
    load_article,
)
from .lexicon import (
    LANGUAGES,
    LEXICON_DIR,
    REVIEW_STATES,
    LexiconResult,
    bundled_catalog_slugs,
    check_lexicon,
    check_term,
    lexicon_status,
    load_catalog_slugs,
    load_lexicon,
    load_term_file,
    review_counts,
)
from .reader import (
    READER_DIR,
    REPOS,
    BridgeEdge,
    ReaderModel,
    load_bridge_graph,
    load_model,
    load_reader_catalog,
    reader_counts,
    reader_status,
)
from .vocabulary import (
    VOCABULARIES,
    VOCABULARY_DIR,
    VocabularyResult,
    canonical_key,
    check_vocabularies,
    check_vocabulary,
    equivalences,
    load_vocabularies,
    load_vocabulary,
    vocabulary_status,
)

__all__ = [
    "LANGUAGES",
    "LEXICON_DIR",
    "REVIEW_STATES",
    "LexiconResult",
    "bundled_catalog_slugs",
    "check_lexicon",
    "check_term",
    "lexicon_status",
    "load_catalog_slugs",
    "load_lexicon",
    "load_term_file",
    "review_counts",
    "VOCABULARIES",
    "VOCABULARY_DIR",
    "VocabularyResult",
    "canonical_key",
    "check_vocabularies",
    "check_vocabulary",
    "equivalences",
    "load_vocabularies",
    "load_vocabulary",
    "vocabulary_status",
    "ArticleResult",
    "article_status",
    "check_article",
    "check_articles",
    "language_coverage",
    "load_article",
    "READER_DIR",
    "REPOS",
    "BridgeEdge",
    "ReaderModel",
    "load_bridge_graph",
    "load_model",
    "load_reader_catalog",
    "reader_counts",
    "reader_status",
    "__version__",
]

__version__ = "0.2.0"
