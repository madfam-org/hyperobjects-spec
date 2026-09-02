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
    "__version__",
]

__version__ = "0.1.0"
