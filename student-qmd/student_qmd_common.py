# check-one-function-per-file: allow-multiple
"""What the student-qmd generator and check share.

make_student_qmd.py writes a student copy line by line; check_student_qmd.py
reads it back with Pandoc. They deliberately share no div or comment parser,
so a mistake in one is caught by the other. What they do share is here:

- which divs only the answer key shows (`hides`), given classes and
  profile attributes each side extracts in its own way;
- where the front matter ends, and how includes resolve.

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


def expand_includes(doc: Path, warn: bool = True) -> list[str]:
    """Return `doc`'s lines with every include shortcode expanded, recursively.

    Like Quarto, this expands an include line wherever it stands, in a code
    block or an HTML comment too. Unlike Quarto, it drops an included file's
    front matter rather than merging it (see `strip_front_matter`).
    """

    def expand(path: Path, seen: tuple[Path, ...]) -> list[str]:
        if path in seen:
            raise StudentQmdError(f"include cycle: {' -> '.join(map(str, seen + (path,)))}")
        if not path.is_file():
            raise StudentQmdError(f"included file not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
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
