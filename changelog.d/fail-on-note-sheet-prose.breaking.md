- **`check-note-sheet-rows` fails on prose and on any list that is not a table or bullets, whatever `fail` says** (#1201).
  A label that is a sentence, words outside math in a formula cell (link text included), and a paragraph outside a table are errors,
  because a note sheet holds formulas under brief labels only (Ezra, 2026-10-22 and 2026-10-23).
  A consumer on `@v3` whose note sheet holds prose goes from green to red when the tag slides;
  lds is the known consumer, and its Midterm 1 note sheet (lds#1267) already passes.
  Wrapped bullet lines, multi-line HTML comments, images, blockquotes and raw HTML lines are allowed.
