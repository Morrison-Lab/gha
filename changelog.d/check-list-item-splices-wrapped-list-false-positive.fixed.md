- **`check_list_item_splices.mjs` no longer false-positives on ordinary wrapped bullet lists** (#895, #896).
  The check previously flagged any list item directly following a non-blank line that was not itself a list item,
  table row, heading, blockquote, or thematic break;
  wrapped continuation lines of a preceding list item triggered the check,
  failing builds on valid tight lists.
  The check now walks back from the preceding line to identify whether it belongs to a preceding list item:
  tight wrapped continuations and indented paragraphs of loose list items are recognized,
  admitting the subsequent list item without requiring an artificial intervening blank line.
  Thematic break detection was also tightened to require matching characters and admit spaced delimiters
  (such as `* * *` and `- - -`) per CommonMark.
