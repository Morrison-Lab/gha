- **check-new-line-breaks now protects bold numbering markers and `ed.` abbreviations**
  from splitting a single sentence into multiple pseudo-sentences.
  Previously, bare bold or emphasized list and numbering markers (such as `**1.**`, `*1.*`, `_1._`, `__1.__`,
  `**1.1.**`, `**a.**`, `**i.**`, `**iv.**`, or `**(1).**`) were treated as complete sentences
  because their trailing emphasis closers matched sentence boundary syntax,
  falsely flagging lines like `**1.** Only the sign constraint.`.
  In addition, `ed.` immediately preceding a citation bracket (such as `(2nd ed.) [@james2021islr]`)
  no longer triggers a false sentence break.
