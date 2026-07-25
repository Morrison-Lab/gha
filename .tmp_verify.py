import sys
sys.path.insert(0, ".github/actions/generate-altdoc-version-dropdown")
from navbar_version import find_versions_entry, set_navbar_title

CONFIG = [
    "website:\n",
    '  title: "$ALTDOC_PACKAGE_NAME"\n',
    "  navbar:\n",
    "    search: true\n",
    "    right:\n",
    "      - text: Versions\n",
    "        menu:\n",
    "          - text: Stable\n",
    "            href: https://example.com/latest-tag/\n",
    "      - icon: github\n",
    "        href: https://example.com/repo\n",
]

config = CONFIG[:2] + ["    title: false\n"] + CONFIG[2:]
_, entry_index, _ = find_versions_entry(config)
lines, title = set_navbar_title(config, entry_index, "<BADGE/>")
print("disabled-title test:", title, lines == config)

config2 = CONFIG[:2] + ['    title: "false"\n'] + CONFIG[2:]
_, entry_index2, _ = find_versions_entry(config2)
lines2, title2 = set_navbar_title(config2, entry_index2, "<BADGE/>")
print("quoted-false test:", title2)
