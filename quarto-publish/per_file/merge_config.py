"""Merge Quarto configuration the way Quarto does."""


def merge_config(base, extra):
    """Merge `extra` into `base`: mappings deeply, lists joined, scalars replaced."""
    for key, value in extra.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            merge_config(base[key], value)
        elif isinstance(base.get(key), list) and isinstance(value, list):
            base[key] = base[key] + value
        else:
            base[key] = value
    return base
