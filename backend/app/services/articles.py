import re
from typing import Any

from sqlalchemy import ColumnElement, String, cast, func, literal_column
from sqlalchemy.dialects.postgresql import TSQUERY

from app.models.article import Article

# Search snippets mark matches with these two characters instead of HTML. The text comes from
# user-written Markdown, so returning markup would make the client trust it. These characters are
# invisible-safe, never valid markup, and trivial for a client to split on and render as <mark>.
HIGHLIGHT_START = "⟦"
HIGHLIGHT_END = "⟧"

_HEADLINE_OPTIONS = (
    f"StartSel={HIGHLIGHT_START}, StopSel={HIGHLIGHT_END}, "
    "MinWords=12, MaxWords=32, ShortWord=2, MaxFragments=1"
)
EXCERPT_LENGTH = 180

# In the lenient tier a match must score at least this share of the best match to be suggested, so
# an article that only shares a common word ("keeps") is not offered next to a real answer.
LENIENT_RELATIVE_CUTOFF = 0.35

# Postgres wants the text-search configuration as a regconfig, not a bound string parameter. This is
# a fixed constant, never user input, so inlining it is safe.
_CONFIG: ColumnElement[Any] = literal_column("'english'::regconfig")


def excerpt(markdown: str, length: int = EXCERPT_LENGTH) -> str:
    """The start of an article as plain text, for lists that are not showing a search match."""
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)  # fenced code blocks
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links and images keep their label
    text = re.sub(r"^[#>\-*+\s]+", "", text, flags=re.MULTILINE)  # heading, quote, list markers
    text = re.sub(r"[`*_~|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + "…"


def search_query(text: str) -> ColumnElement[object]:
    """Strict search: every word must match, quoted phrases and -exclusions work like a web search.

    websearch_to_tsquery never raises on odd input, so user text is safe to pass straight in.
    """
    return func.websearch_to_tsquery(_CONFIG, text)


def all_words_query(text: str) -> ColumnElement[object]:
    """Every word must match, with no web-search syntax. The first, precise tier of suggestions."""
    return func.plainto_tsquery(_CONFIG, text)


def suggestion_query(text: str) -> ColumnElement[object]:
    """Lenient search for suggestions: an article matching *any* of the words qualifies.

    A ticket title like "VPN keeps dropping" should find the VPN article even though it never says
    "keeps". plainto_tsquery joins the words with &, so swap those for | and cast back.
    """
    anded = cast(func.plainto_tsquery(_CONFIG, text), String)
    return cast(func.replace(anded, "&", "|"), TSQUERY())  # type: ignore[arg-type]


def plain_body() -> ColumnElement[str]:
    """The article text with Markdown syntax removed, so snippets read as sentences.

    Code blocks are dropped, links keep their label but not their address, and the characters that
    only exist to format (# > * _ ` ~ | and runs of dashes) are removed. This is for display only:
    matching still runs against the search_vector built from the original text.
    """
    text = func.regexp_replace(Article.body, "```[^`]*```", " ", "g")
    text = func.regexp_replace(text, r"!?\[([^\]]*)\]\([^)]*\)", r"\1", "g")
    # Emphasis markers vanish without trace, so "**word**." stays "word.". Structural ones become
    # spaces, and runs of dashes (table separator rows, rules) are dropped too.
    text = func.regexp_replace(text, r"[*_`~]+", "", "g")
    return func.regexp_replace(text, r"[#>|]+|-{3,}", " ", "g")


def headline(query: ColumnElement[object]) -> ColumnElement[str]:
    return func.ts_headline(_CONFIG, plain_body(), query, _HEADLINE_OPTIONS)


# ts_rank normalisation flag 1 divides by 1 + log(document length), so a long article that happens
# to mention a word once cannot outscore a focused one. Used where weak matches are being pruned.
NORMALISE_BY_LENGTH = 1


def rank(query: ColumnElement[object], normalisation: int = 0) -> ColumnElement[float]:
    return func.ts_rank(Article.search_vector, query, normalisation)
