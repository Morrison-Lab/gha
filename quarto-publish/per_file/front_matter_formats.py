"""The output formats a file declares."""
import pathlib

import yaml

from per_file.format_names import format_names


def front_matter_formats(path, config):
    """Format names in the file's front matter, else the project's `format:`."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            try:
                meta = yaml.safe_load(text[3:end]) or {}
            except yaml.YAMLError:
                meta = {}
    declared = format_names(meta.get("format")) if isinstance(meta, dict) else set()
    return declared or format_names(config.get("format"))
