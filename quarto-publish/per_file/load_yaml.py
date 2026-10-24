"""Read a YAML file as a dict."""
import yaml


def load_yaml(path):
    """The mapping in `path`, or an empty one if it cannot be read or parsed."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
