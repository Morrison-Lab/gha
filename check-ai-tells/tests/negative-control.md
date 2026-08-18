# Negative Control for AI Tells

This document contains standard technical documentation and plain prose.

We describe an implementation of a diff parser that maps unified diff hunks
to line numbers. The script parses line prefixes, checks for headers, and
tracks line indices sequentially.

Testing is done with unit tests that compare expected outputs against actual
values. The functions run in batch mode and return integer vectors.
