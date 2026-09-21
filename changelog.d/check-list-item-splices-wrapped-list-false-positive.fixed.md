- **`check_list_item_splices.mjs` no longer false-positives on ordinary wrapped bullet lists** (#895, #896).
  The check previously flagged any list item directly following a non-blank line that was not itself a list item,
  table row, heading, blockquote, or thematic break;
  wrapped continuation lines of a preceding list item triggered the check,
  failing builds on valid tight lists.
  The check now walks back from the preceding line to the start of its non-blank block:
  if the block began with a list marker,
  the preceding line is recognized as a list-item continuation line rather than a paragraph continuation line,
  and the subsequent list item is admitted without requiring an artificial intervening blank line.
