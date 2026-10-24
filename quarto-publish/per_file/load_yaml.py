"""Read a YAML file as a dict."""


def load_yaml(path):
    """The mapping in `path`, or an empty one if it cannot be read or parsed."""
    import yaml  # only the fallback needs PyYAML, so a working inspect does not
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
