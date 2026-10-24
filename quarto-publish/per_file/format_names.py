"""Format names from a Quarto `format:` value."""


def format_names(value):
    """The format names in a string, a mapping's keys, or a list of either."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set(value)
    if isinstance(value, list):
        names = set()
        for item in value:
            names |= format_names(item)
        return names
    return set()
