# check-one-function-per-file: allow-multiple
"""What the student-qmd generator and check share.

make_student_qmd.py writes a student copy line by line; check_student_qmd.py
reads it back with Pandoc. They deliberately share no parser for removing
divs and comments, so a mistake in one is caught by the other. What they do
share is here:

- which divs only the answer key shows (`hides`), given classes and
  profile attributes each side extracts in its own way;
- where the front matter ends, and how includes resolve;
- the refusal of an answer written in a raw HTML `<div>` (`raw_answer_divs`).
  Pandoc reads `<div class="sol">` as the same div as `::: {.sol}`, so the
  assign filter hides it, but the generator removes only `:::` divs and would
  copy it into the student file. Rather than parse HTML nesting line by line,
  both halves refuse such a source, naming the file and line, whether or not
  the check runs.

Include resolution is shared rather than duplicated because it must match
Quarto, not merely agree with itself: Quarto resolves every include,
however deeply nested, against the directory of the document being
rendered, and a path starting with `/` against the project root. Both
halves resolving a nested include against the including file instead would
agree with each other and still write the wrong file. The selftest renders
a fixture where the two rules pick different files, to pin this against
Quarto itself.
"""

from __future__ import annotations

import glob
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

INCLUDE = re.compile(r"^\s*\{\{<\s*include\s+(\S+)\s*>\}\}\s*$")

# The classes the coatless-quarto/assign filter hides from the student copy:
# `.sol` shows only under the `solution` (or `rubric`) profile, `.rubric`
# only under `rubric`. `.direction` shows only under `assign`, so it is
# student content and not in this list.
DEFAULT_HIDDEN_CLASSES = ("sol", "rubric")
# Profiles whose `when-profile` content is for the answer key only.
DEFAULT_ANSWER_PROFILES = ("solution", "solutions", "rubric")
DEFAULT_STUDENT_PROFILE = "assign"

# Div classes that look like an answer but name no hidden class. The assign
# filter passes such a div through untouched, so its text reaches every render
# and the student file, and nothing else would notice.
MISNAMED_ANSWER = frozenset(
    {"solution", "solutions", "soln", "answer", "answers", "ans", "answer-key", "key"}
)


FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+).*?(?<!`)\1(?!`)")
# A raw HTML div start tag, which Pandoc's native_divs extension (on by
# default) reads as a Div node. The tag may run onto later lines, and a
# quoted attribute value may hold a `>`.
RAW_DIV = re.compile(r"""<div(?=[\s/>]|$)(?:[^>"']|"[^"]*"|'[^']*')*""", re.IGNORECASE)
HTML_ATTR = re.compile(r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")
VISIBILITY_CLASSES = frozenset({"content-visible", "content-hidden"})
# Pandoc keeps a `data-` prefix, so `data-when-profile` reaches Quarto under
# that name; it is refused too, since an author writing it meant a profile.
PROFILE_ATTRS = frozenset(
    {"when-profile", "unless-profile", "data-when-profile", "data-unless-profile"}
)
# How many lines a raw div start tag may run onto.
MAX_TAG_LINES = 20


class StudentQmdError(Exception):
    """A source the tools refuse to process, rather than guess about."""


@dataclass(frozen=True)
class Config:
    hidden_classes: frozenset[str] = frozenset(DEFAULT_HIDDEN_CLASSES)
    answer_profiles: frozenset[str] = frozenset(DEFAULT_ANSWER_PROFILES)
    student_profile: str = DEFAULT_STUDENT_PROFILE
    drop_render_chunks: bool = False
    misnamed: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        if not self.hidden_classes:
            raise StudentQmdError("hidden-classes is empty, so no answer would be removed")
        if not self.student_profile or re.search(r"[\s,]", self.student_profile):
            raise StudentQmdError(
                f"student-profile must be one profile name, got {self.student_profile!r}"
            )
        # A class the caller hides is not misnamed.
        object.__setattr__(self, "misnamed", MISNAMED_ANSWER - self.hidden_classes)


def split_list(value: str) -> list[str]:
    """Split a comma-, space- or newline-separated input into its items."""
    return [item for item in re.split(r"[\s,]+", value.strip()) if item]


def parse_bool(value: str, name: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0", ""):
        return False
    raise StudentQmdError(f"{name} must be true or false, got {value!r}")


def profile_names(value: str) -> set[str]:
    return set(split_list(value))


def hides(classes: set[str], profile_attrs: list[tuple[str, str]], cfg: Config) -> bool:
    """Whether a div with these classes and profile attributes is answer-key-only.

    That is a div with a hidden class, or a Quarto profile-visibility div
    shown only under an answer profile: content-visible when an answer
    profile, content-visible unless the student profile, content-hidden
    unless an answer profile, content-hidden when the student profile.
    `profile_attrs` holds (`when-profile` or `unless-profile`, value) pairs.

    A value naming several profiles is split into its names. Quarto 1.10.18
    does not split it: rendering `when-profile="assign,solution"` (or
    `"assign solution"`) under each of the assign, solution and an unrelated
    profile showed that Quarto compares the whole value as one profile name,
    so `when-profile` with a list never matches and `unless-profile` with a
    list always does. Splitting still removes every div that could carry an
    answer (a list naming an answer profile is removed, and Quarto never
    shows it anyway), so the student file cannot leak one. The cost is in
    the other direction: `content-visible unless-profile` and
    `content-hidden when-profile` with a list naming the student profile are
    removed here, though Quarto shows them under every profile.
    """
    if classes & cfg.hidden_classes:
        return True
    for key, value in profile_attrs:
        names = profile_names(value)
        answer = bool(names & cfg.answer_profiles)
        student = cfg.student_profile in names
        if "content-visible" in classes and (
            (key == "when-profile" and answer) or (key == "unless-profile" and student)
        ):
            return True
        if "content-hidden" in classes and (
            (key == "unless-profile" and answer) or (key == "when-profile" and student)
        ):
            return True
    return False


def front_matter_end(lines: list[str]) -> int:
    """Index of the line closing the leading YAML front matter, or 0 if none.

    As in YAML, only an unindented `---` or `...` ends it: an indented `---`
    is text inside a multi-line value.
    """
    if lines and lines[0].rstrip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.rstrip() in ("---", "..."):
                return i
    return 0


def strip_front_matter(lines: list[str], source: Path | None = None) -> list[str]:
    """Drop an included file's leading YAML front matter block.

    Quarto does not drop it: it merges an included file's front matter into
    the document's metadata. A student copy drops it anyway, because the
    front matter a question fragment carries names the assign filter, and
    that filter is not there when a student renders the file on its own.
    Anything else in it would be lost, so a key other than `filters` is
    warned about (for `source`, when given) rather than dropped silently.
    """
    end = front_matter_end(lines)
    if not end:
        return lines
    if source is not None:
        extra = [
            line.split(":", 1)[0]
            for line in lines[1:end]
            if line.strip()
            and not line.lstrip().startswith("#")
            and not line[0].isspace()
            and not line.startswith("filters:")
        ]
        if extra:
            print(
                f"::warning::{source}: the student copy drops this included file's front matter,"
                f" which Quarto would merge into the document; it sets {', '.join(extra)}"
            )
    return lines[end + 1 :]


def project_root(doc: Path) -> Path | None:
    """The nearest directory at or above `doc`'s holding a Quarto project file."""
    for directory in doc.resolve().parents:
        if (directory / "_quarto.yml").is_file() or (directory / "_quarto.yaml").is_file():
            return directory
    return None


def resolve_include(target: str, doc: Path) -> Path:
    """Where Quarto finds `target` when rendering `doc`.

    A relative path is relative to `doc`'s directory, even for an include
    inside an included file; a path starting with `/` is relative to the
    project root.
    """
    if target.startswith("/"):
        root = project_root(doc)
        if root is None:
            raise StudentQmdError(
                f"{doc}: include {target} starts with /, but no _quarto.yml was found above it"
            )
        return (root / target.lstrip("/")).resolve()
    return (doc.resolve().parent / target).resolve()


def expand_includes(
    doc: Path, warn: bool = True, visit: Callable[[Path, list[str]], None] | None = None
) -> list[str]:
    """Return `doc`'s lines with every include shortcode expanded, recursively.

    Like Quarto, this expands an include line wherever it stands, in a code
    block or an HTML comment too. Unlike Quarto, it drops an included file's
    front matter rather than merging it (see `strip_front_matter`). `visit`,
    when given, is called with each file read and its own lines, so a
    problem can be reported against the file and line it is on.
    """

    def expand(path: Path, seen: tuple[Path, ...]) -> list[str]:
        if path in seen:
            raise StudentQmdError(f"include cycle: {' -> '.join(map(str, seen + (path,)))}")
        if not path.is_file():
            raise StudentQmdError(f"included file not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        if visit is not None:
            visit(path, lines)
        if seen:
            lines = strip_front_matter(lines, path if warn else None)
        out: list[str] = []
        for line in lines:
            m = INCLUDE.match(line)
            if m:
                out.extend(expand(resolve_include(m.group(1), doc), seen + (path,)))
            else:
                out.append(line)
        return out

    return expand(doc.resolve(), ())


def fence_closes(line: str, fence: str) -> bool:
    """A fence closes on a run of the same character at least as long as the
    opener, with nothing else on the line."""
    run = line.strip()
    return bool(run) and set(run) == {fence[0]} and len(run) >= len(fence)


def visible_text(line: str, in_comment: bool) -> tuple[str, bool]:
    """`line` with HTML comments and code spans blanked out, and whether a
    comment is still open at its end."""
    spans = [m.span() for m in CODE_SPAN.finditer(line)]
    out = []
    i = 0
    while i < len(line):
        if in_comment:
            end = line.find("-->", i)
            if end < 0:
                break
            in_comment = False
            i = end + 3
        elif span := next((b for a, b in spans if a == i), None):
            out.append(" ")
            i = span
        elif line.startswith("<!--", i):
            in_comment = True
            i += 4
        else:
            out.append(line[i])
            i += 1
    return "".join(out), in_comment


def raw_div_hides(tag: str, cfg: Config) -> bool:
    """Whether a raw `<div ...` start tag names a hidden class, or a
    profile-visibility class with any profile attribute.

    This errs toward refusing: a profile div is refused whichever profile it
    names, since writing it with `:::` costs nothing.
    """
    attrs = {}
    for m in HTML_ATTR.finditer(tag[len("<div") :]):
        # Pandoc, like the HTML parsing spec, keeps the first of a repeated
        # attribute, so `<div class="sol" class="note">` is a .sol div.
        value = next((v for v in m.groups()[1:] if v is not None), "")
        attrs.setdefault(m.group(1).lower(), value)
    classes = set(attrs.get("class", "").split())
    if classes & cfg.hidden_classes:
        return True
    return bool(classes & VISIBILITY_CLASSES and PROFILE_ATTRS & attrs.keys())


def raw_answer_divs(path: Path, lines: list[str], cfg: Config) -> list[str]:
    """One message per raw HTML `<div>` in `lines` that hides an answer.

    Code blocks, code spans and HTML comments are skipped. Anything else
    that looks like such a tag is reported, including one Pandoc would not
    read as a div (in an indented code block, say): this errs toward
    refusing.
    """
    found = []
    fence = ""
    in_comment = False
    for n, line in enumerate(lines, start=1):
        if fence:
            if fence_closes(line, fence):
                fence = ""
            continue
        if not in_comment and (m := FENCE.match(line)):
            fence = m.group(1)
            continue
        text, in_comment = visible_text(line, in_comment)
        for m in re.finditer(r"<div(?=[\s/>]|$)", text, re.IGNORECASE):
            tail = " ".join([text[m.start() :], *lines[n : n + MAX_TAG_LINES]])
            tag = RAW_DIV.match(tail)
            if tag and raw_div_hides(tag.group(0), cfg):
                found.append(
                    f"{path}:{n}: an answer in a raw HTML <div>, which the student copy "
                    "cannot remove; write it as a ::: div, such as ::: {.sol}"
                )
    return found


def find_sources(patterns: list[str]) -> list[Path]:
    """Expand each path or glob, in order, without duplicates.

    A pattern matching nothing is warned about rather than refused, so a
    caller can list a directory that has no sources yet (exams, say, before
    the first is written); matching nothing at all is an error.
    """
    if not patterns:
        raise StudentQmdError("no sources given")
    found: list[Path] = []
    for pattern in patterns:
        matches = sorted(Path(p) for p in glob.glob(pattern, recursive=True) if Path(p).is_file())
        if not matches:
            print(f"::warning::source pattern {pattern!r} matched no file")
        for match in matches:
            if match not in found:
                found.append(match)
    if not found:
        raise StudentQmdError(f"no source matched any of {', '.join(map(repr, patterns))}")
    return found


def output_path(out_dir: Path, source: Path) -> Path:
    return out_dir / source.name


def check_unique_names(sources: list[Path]) -> None:
    seen: dict[str, Path] = {}
    for src in sources:
        if src.name in seen:
            raise StudentQmdError(
                f"{seen[src.name]} and {src} would both write {src.name} in the output directory"
            )
        seen[src.name] = src
