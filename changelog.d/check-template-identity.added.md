- **`check-template-identity`**
  ([#2154](https://github.com/Morrison-Lab/gha/issues/2154)):
  add a blocking composite action and reusable workflow for template repositories.
  It fails a repository made from the template
  while its config files still hold the template's repository URL, Pages URL,
  or a listed literal such as the template's title.
  It passes with a notice in the template itself,
  and stops with an error when it read no file.
