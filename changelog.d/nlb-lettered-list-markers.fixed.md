- **`check-new-line-breaks` no longer flags lettered list items.**
  A list item opened with a letter marker, such as `a.` or `B.` followed by a space,
  kept its marker when the line was measured,
  so each sub-part of a lettered exercise read as a packed line.
  The marker is now stripped, as a numbered one already was.
