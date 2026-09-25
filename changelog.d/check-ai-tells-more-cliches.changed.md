- **`check-ai-tells` catches more AI clichés.**
  Adds 13 lexical tells and seven rhetorical patterns:
  throat-clearing lead-in, answered rhetorical question, assistant chatter,
  not-because reframe, personified abstraction, editorializing tail,
  and inflated copula (limited to a closed set of metaphorical nouns).
  The multi-word names that `ignore-tells` recognizes are now derived from
  the catalog, so a new pattern name is never split into single words.
  The reference page now names
  [*Principles of Scientific Writing*](https://morrison-lab.github.io/psw/chapters/avoid-ai-tells.html)
  as the canonical list this catalog draws from,
  and the test suite checks the lexical tells against a psw checkout
  when `PSW_AI_TELLS_FILE` is set.
