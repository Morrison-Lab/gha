"""The project's Quarto configuration."""
import os
import pathlib

from per_file.load_yaml import load_yaml
from per_file.merge_config import merge_config


def project_config(project):
    """`_quarto.yml` merged with the profile files named in QUARTO_PROFILE."""
    config = {}
    profile = os.environ.get("QUARTO_PROFILE", "")
    names = ["_quarto.yml", "_quarto.yaml"]
    names += [f"_quarto-{p}.{ext}" for p in profile.split(",") if p
              for ext in ("yml", "yaml")]
    for name in names:
        path = pathlib.Path(project) / name
        if path.exists():
            merge_config(config, load_yaml(path))
    return config
