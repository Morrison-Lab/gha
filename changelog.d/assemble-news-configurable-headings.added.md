- **`assemble-news` gains a `headings` input** (#562).
  The category-to-heading map was hard-coded to four R-package sections,
  so a consumer whose `NEWS.md` uses a richer taxonomy had to choose
  between the fragment workflow and its own changelog structure.
  The input takes newline-separated `category = Heading` pairs and,
  when set, replaces the built-in map entirely,
  defining both the recognized category set and the heading display order.
  Leaving it empty is exactly the previous behavior,
  so existing consumers are unaffected.
