- **New `check-quarto-prose` capability.**
  A diff-scoped, blocking check over `.qmd` and `.md` files that reports two rules as `::error file=,line=::` annotations.
  `notes-div-content` flags a `::: notes` div that holds a nested div with an `exm-`, `rem-`, `def-`, `thm-` or `exr-` id, or whose first non-blank line starts with `Example`, `Remark` or `Note:`, because that content belongs in the slide body.
  `banned-idiom` flags a case-insensitive whole-phrase match against a list of idioms, cliches and slang, bundled in `check-quarto-prose/banned-idioms.txt` or replaced with the `idioms-file` input.
  A line is exempted with `<!-- prose-allow: phrase -->`, or a file with the `allow-file` input.
  Code fences, inline code, math, HTML comments and front matter other than `title`, `subtitle` and `description` are never scanned.
  Like `check-typos`, it reports only the lines a diff adds, and with no `base-ref` it skips rather than scanning the whole tree.
  Ships at `@v3`.
