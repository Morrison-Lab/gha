"""The project's Quarto configuration."""
import os
import pathlib

from per_file.load_yaml import load_yaml
from per_file.merge_config import merge_config


def project_config(project):
    """`_quarto.yml` merged with the profile files of the active profiles.

    The active profiles are those in QUARTO_PROFILE, else the `profile: default:`
    of `_quarto.yml`, as in Quarto.
    """
    config = {}
    base = pathlib.Path(project)
    for name in ("_quarto.yml", "_quarto.yaml"):
        if (base / name).exists():
            merge_config(config, load_yaml(base / name))
    profiles = [p for p in os.environ.get("QUARTO_PROFILE", "").split(",") if p]
    if not profiles:
        default = (config.get("profile") or {}).get("default") or []
        profiles = [default] if isinstance(default, str) else list(default)
    for profile in profiles:
        for ext in ("yml", "yaml"):
            path = base / f"_quarto-{profile}.{ext}"
            if path.exists():
                merge_config(config, load_yaml(path))
    return config
