"""The files a project's `render:` globs select."""
import fnmatch
import pathlib


def project_inputs(project, config):
    """Absolute paths of the `.qmd` files the `render:` globs select, as Quarto would.

    A `!` entry excludes: a trailing `/` excludes a directory, anything else is
    a glob.  Files and directories starting with `_` or `.` are never inputs.
    """
    root = pathlib.Path(project)
    patterns = (config.get("project") or {}).get("render") or ["*.qmd"]
    include = [p for p in patterns if not p.startswith("!")]
    exclude = [p[1:] for p in patterns if p.startswith("!")]
    found = set()
    for pattern in include:
        for path in root.glob(pattern):
            rel = path.relative_to(root)
            if (path.is_file() and path.suffix == ".qmd"
                    and not any(part.startswith(("_", ".")) for part in rel.parts)):
                found.add(rel.as_posix())

    kept = [
        rel for rel in found
        if not any(
            rel.startswith(pattern) if pattern.endswith("/")
            else fnmatch.fnmatch(rel, pattern)
            for pattern in exclude
        )
    ]
    return sorted(str(root / rel) for rel in kept)
