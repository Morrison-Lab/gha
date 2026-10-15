- **`check-new-line-breaks` no longer flags lettered list items.**
  A list item opened with a lowercase letter marker followed by a space, such as `a.`,
  or an uppercase one followed by two spaces, such as `B.`,
  kept its marker when the line was measured,
  so each sub-part of a lettered exercise read as a packed line.
  The marker is now stripped, as a numbered one already was.
  A single uppercase letter and one space, as in an initial ("J. Smith"), stays prose.
