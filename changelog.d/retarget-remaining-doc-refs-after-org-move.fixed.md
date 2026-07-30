- **The docs site no longer advertises a dead canonical URL**, and the last
  stale `d-morrison/gha` self-references are gone (#364, follow-up to the
  earlier doc-URL retarget).

  `website/_quarto.yml` was missed by that sweep entirely.
  Its `site-url` pointed at `https://d-morrison.github.io/gha/`, which
  returns 404 while the real site returns 200, so Quarto was emitting a dead
  base URL in canonical links, the sitemap, and social metadata.
  Its `title`, `repo-url`, and the navbar's GitHub link named the old owner
  too.
  The `description`'s consumer list is untouched: `d-morrison` is still one
  of the orgs whose repositories call these workflows.

  Three reusable workflows embedded the old owner in a markdown link written
  into every consumer's generated PR body, so those shipped outward rather
  than merely sitting in this repo: `sync-upstream.yml`, `bump-submodule.yml`,
  and `sync-shared-fragments.yml`.

  Three comments had become false rather than stale, since the code they
  describe already says `Morrison-Lab/gha/...@v2`: `_selftest.yml`'s
  request-dependabot-review note, `dependabot-review.yml`'s header, and
  `dependabot.yml`'s first-party-exemption note.
  The remaining self-references were swept alongside them: six
  `.github/actions/*/action.yml` headers describing "not `d-morrison/gha`'s
  own tree", the same phrasing where `claude.yml` and `claude-code-review.yml`
  explain why their steps run against the caller's checkout,
  `check-links/lychee.default.toml`'s header, and the two `parse-workflow-ref`
  test cases whose input strings named the old path.

  `generate-altdoc-version-dropdown` needed more than a rename.
  Its `GENERATED_MARKER` is written into each consumer's navbar config and
  matched back by exact string on the next run, and by then the rewrite has
  already replaced the `- text: Versions` anchor with the version label, so
  the marker is the only thing left to match.
  Renaming it alone would have stranded every already-generated consumer and
  stacked a second dropdown instead of replacing the first.
  The old spelling is now recognised on read while only the new one is
  written, with a regression test covering a pre-move config.

  Historical references keep the name the repository had when they were
  written: `CHANGELOG.md`, existing `changelog.d/` entries, `gha#336`-style
  issue citations, `CLAUDE.md`'s account of the move, and `REVDEPS.md`'s
  deliberate instruction to search the old path for unmigrated consumers.
