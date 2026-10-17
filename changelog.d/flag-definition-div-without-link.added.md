- **`check-informal-definitions` flags a definition div that links no other
  term** (`no-link-in-definition`), a decidable proxy for "hyperlink every
  technical term on first use in each div" (ai-config#4600).
  The check is warn-only by default, like the rest of the action, and the
  existing `<!-- check-informal-definitions: allow -->` opt-out covers a
  foundational definition that has nothing to link.
