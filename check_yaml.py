import yaml

files = [
    'examples/check-bibliography-dois.yml',
    'examples/check-phi.yml',
    'examples/check-links.yml',
    'examples/check-non-standard-chars.yml',
    'examples/claude.yml',
    'examples/claude-code-review.yml',
    'examples/update-snapshots.yml',
]
for f in files:
    with open(f) as fh:
        yaml.safe_load(fh)
    print(f, 'OK')
