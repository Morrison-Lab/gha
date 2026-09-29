- **`check-merge-drops` scopes near-twins to resolution lines, supports bullet splits, and adds octopus test** (#966).
  The near-twin rewording check previously compared against all lines in the merge file,
  which could hide a dropped line when an unrelated parent or base line had similar wording.
  Near-twin comparisons are now scoped exclusively to lines newly introduced in the merge relative to all parents.
  Line-leading list item markers (`-`, `*`, `+`, `1.`) are now stripped during whitespace-flattened comparisons
  so paragraphs split into bulleted items during resolution are not reported as drops.
  Added unit tests for octopus merges with three parents and updated the skip warning for missing merge bases.
