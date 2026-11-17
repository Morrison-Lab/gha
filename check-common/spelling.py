# check-one-function-per-file: allow-multiple
"""British spellings and their American forms (gha#2095).

One copy of the word list: ``check-avoided-words`` flags ``BRITISH_RE`` in
prose, and ``diffscope.parse_diff`` uses ``americanize_line`` so that a line
whose only change is British to American spelling counts as unchanged, not
added.  Without that, a spelling fix makes every other diff-scoped check
re-read the whole line and reflag what it already carried.

The list is explicit, never a bare "-ise" pattern, which would flag
"otherwise", "noise", "exercise" and "precise".  "analyses" passes: it is
also the plural noun.

Stdlib only, like the checks that import it.
"""

import re

_IS_STEMS = (
    "optim|minim|maxim|normal|standard|regular|general|character|summar|"
    "visual|initial|organ|recogn|real|parameter|parametr|emphas|random|"
    "vector|discret|linear|penal|util|special|token|factor|memor|theor|"
    "hypothes|symbol|critic|apolog|priorit|final|custom|local|capital|"
    "central|stabil|harmon|synchron|author|sanit|serial|polar|modern|"
    "rational|familiar|conceptual|contextual|operational|orthogonal|"
    "diagonal|marginal|binar|dichotom|winsor|lemmat|anonym|digit|categor|"
    "item|individual|personal|neutral|nominal|equal|scrutin|sympath"
)
_OUR_STEMS = (
    "colo|behavio|favo|hono|labo|neighbo|flavo|humo|rumo|vapo|harbo|"
    "armo|endeavo|savo|odo|vigo|rigo|tumo|fervo|paro|clamo|cando|splendo"
)
_RE_WORDS = "metre|litre|fibre|centre|theatre|spectre|calibre|lustre|sombre"
_LL_STEMS = (
    "model|label|travel|cancel|signal|level|tunnel|fuel|total|channel|"
    "counsel|marshal|dial|pencil|quarrel"
)

_CORE = (
    r"(?:"
    r"(?:" + _OUR_STEMS + r")"
    r"ur(?:s|ed|ing|ful|less|al|ally|ite|ites|able|ably|hood|hoods|map|maps|"
    r"bar|bars|scale|scales|blind|ation|ations)?"
    r"|(?:" + _IS_STEMS + r")is(?:e|es|ed|ing|er|ers|able|ation|ations|"
    r"ational)"
    r"|(?:ana|para|cata|dia|electro|hydro)lys(?:e|ed|ing|er|ers)"
    r"|(?:centi|milli|kilo|nano|micro)?metres?|centre(?:s|d)?|centring"
    r"|litres?|fibres?|theatres?|spectres?|calibres?|sombre|lustre"
    r"|manoeuvr(?:e|es|ed|ing)"
    r"|(?:" + _LL_STEMS + r")l(?:ed|ing|er|ers)"
    r"|fulfil(?:s|ment)?|enrol(?:s|ment|ments)?|skilful(?:ly)?|wilful(?:ly)?"
    r"|instalments?|jewellery"
    r"|defences?|offences?|licences?|pretences?"
    r"|anaemi[ac]|haem\w*|oesophag\w*|foet(?:us|uses|al)|paediatric\w*"
    r"|orthopaedic\w*|leukaemia|oestrogen|diarrhoea|encyclopaedi\w*"
    r"|grey(?:s|ed|er|est|ish|scale)?|whilst|amongst|learnt|per\s+cent"
    r"|judgements?|acknowledgements?|ageing|artefacts?|catalogu(?:e|es|ed|ing)"
    r"|programmes?|sceptic(?:al|ism|s)?|aluminium|cheques?|tyres?"
    r"|mould(?:s|ed|ing|y)?|plough(?:s|ed|ing)?|focuss(?:ed|es|ing)"
    r")"
)
# A prefix keeps the spelling of the word it is on: unlabelled, recoloured.
_PREFIXES = "un|re|mis|non|pre|over|under|sub|de"
_CORE_RE = re.compile(r"(?i)" + _CORE)
_PREFIX_RE = re.compile(r"(?i)^(" + _PREFIXES + r")(-?)(.+)$")
BRITISH_RE = re.compile(r"(?i)\b(?:(?:" + _PREFIXES + r")-?)?" + _CORE + r"\b")

# Whole words whose American form no suffix rule gives.
_WHOLE = {
    "grey": "gray", "greys": "grays", "greyed": "grayed", "greyer": "grayer",
    "greyest": "grayest", "greyish": "grayish", "greyscale": "grayscale",
    "judgement": "judgment", "judgements": "judgments",
    "acknowledgement": "acknowledgment", "acknowledgements": "acknowledgments",
    "defence": "defense", "defences": "defenses", "offence": "offense",
    "offences": "offenses", "licence": "license", "licences": "licenses",
    "pretence": "pretense", "pretences": "pretenses",
    "whilst": "while", "amongst": "among", "learnt": "learned",
    "ageing": "aging", "artefact": "artifact", "artefacts": "artifacts",
    "centred": "centered", "centring": "centering",
    "enrolment": "enrollment", "enrolments": "enrollments",
    "fulfilment": "fulfillment",
    "catalogue": "catalog", "catalogues": "catalogs", "catalogued": "cataloged",
    "cataloguing": "cataloging", "programme": "program", "programmes": "programs",
    "aluminium": "aluminum", "fulfil": "fulfill", "fulfils": "fulfills",
    "skilful": "skillful", "skilfully": "skillfully", "wilful": "willful",
    "wilfully": "willfully", "instalment": "installment",
    "instalments": "installments", "jewellery": "jewelry",
    "enrol": "enroll", "enrols": "enrolls",
    "manoeuvre": "maneuver", "manoeuvres": "maneuvers",
    "manoeuvred": "maneuvered", "manoeuvring": "maneuvering",
    "per cent": "percent",
}


def americanize(word: str) -> str:
    """The American spelling of a word ``BRITISH_RE`` matches, in its case."""
    low = word.lower()
    split = _PREFIX_RE.match(word)
    if not _CORE_RE.fullmatch(low) and split and _CORE_RE.fullmatch(split.group(3)):
        return split.group(1) + split.group(2) + americanize(split.group(3))
    if low in _WHOLE:
        new = _WHOLE[low]
    else:
        new = re.sub(r"^((?:" + _OUR_STEMS + r"))ur", r"\1r", low)
        new = re.sub(r"lys(e|ed|ing|er|ers)$", r"lyz\1", new)
        new = re.sub(r"(" + _IS_STEMS + r")is(e|es|ed|ing|er|ers|able|ation|"
                     r"ations|ational)$", r"\1iz\2", new)
        new = re.sub(r"(" + _RE_WORDS + r")(s?)$",
                     lambda m: m.group(1)[:-2] + "er" + m.group(2), new)
        new = re.sub(r"^(" + _LL_STEMS + r")l(ed|ing|er|ers)$", r"\1\2", new)
        new = re.sub(r"^(an)ae(mi[ac])$", r"\1e\2", new)
        new = re.sub(r"^haem", "hem", new)
        new = re.sub(r"^oe", "e", new)
        new = re.sub(r"^foet", "fet", new)
        new = re.sub(r"paed", "ped", new)
        new = re.sub(r"leukaem", "leukem", new)
        new = re.sub(r"rrhoea$", "rrhea", new)
        new = re.sub(r"^sceptic", "skeptic", new)
        new = re.sub(r"^mould", "mold", new)
        new = re.sub(r"^plough", "plow", new)
        new = re.sub(r"^focuss", "focus", new)
        new = re.sub(r"^cheque", "check", new)
        new = re.sub(r"^tyre", "tire", new)
    if word.isupper():
        return new.upper()
    if word[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def americanize_line(text: str) -> str:
    """``text`` with every British spelling in it replaced by its American form."""
    return BRITISH_RE.sub(lambda m: americanize(m.group(0)), text)


_CODE_SPAN_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


def americanize_prose(text: str) -> str:
    """``americanize_line`` outside code spans, which keep their spelling."""
    out, last = [], 0
    for span in _CODE_SPAN_RE.finditer(text):
        out.append(americanize_line(text[last:span.start()]))
        out.append(span.group(0))
        last = span.end()
    out.append(americanize_line(text[last:]))
    return "".join(out)


def american_variants(text: str) -> set:
    """The respellings of a deleted line that a spelling-only fix could give.

    Empty when the line has no British spelling.  A fix may respell code
    spans too, or leave them, so both forms count.
    """
    return {americanize_line(text), americanize_prose(text)} - {text}
