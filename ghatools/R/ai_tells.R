#' Patterns for the AI tells catalogued in ai-config
#'
#' A named list of PCRE patterns, one per tell category, composed with
#' [rex::rex()] rather than written as raw regex strings: these are read far
#' more often than written, and a hand-rolled alternation is where the mistakes
#' hide.
#'
#' The categories follow ai-config's `shared/writing/ai-tells.md`. That
#' catalog's operative sentence governs how the patterns should be *used*:
#' "Any single tell is innocent; clustering and mechanical repetition are the
#' signal."
#'
#' So a caller should report density and co-occurrence rather than flagging
#' every individual match. A check that fires on each "robust" would fire
#' constantly on legitimate technical prose and train its readers to ignore it.
#'
#' @returns A named list of character patterns.
#' @export
ai_tell_patterns <- function() {
  words <- function(...) rex::rex(boundary, or(...), boundary)
  list(
    overused_vocabulary = words(
      "delve", "delves", "delving",
      "leverage", "leverages", "leveraging",
      "utilize", "utilizes", "utilizing", "utilise", "utilises",
      "tapestry", "testament", "realm", "seamless", "seamlessly",
      "holistic", "multifaceted", "pivotal",
      "showcase", "showcases", "showcasing",
      "underscore", "underscores", "underscoring",
      "actionable"
    ),
    # The catalog names this the biggest tell.
    not_just_antithesis = rex::rex(
      "not just ", anything,
      or(", it", "; it", " but "), maybe(" is"), maybe("'s")
    ),
    not_only_but = rex::rex("not only ", anything, " but ", maybe("also ")),
    signposting_filler = words(
      "it's worth noting", "it is worth noting", "it should be noted",
      "importantly,", "notably,", "crucially,", "fundamentally,",
      "in essence", "at its core", "needless to say"
    ),
    hollow_conclusion = words(
      "in conclusion", "to summarize", "to summarise", "in summary",
      "all in all"
    ),
    promotional = words(
      "cutting-edge", "state-of-the-art", "game-changing", "revolutionary",
      "rich set of", "wide range of", "comprehensive suite",
      "in today's fast-paced", "stands as a testament"
    ),
    vague_universal = words(
      "a variety of", "various aspects", "many different",
      "a range of factors", "a myriad of"
    )
  )
}

#' Which lines of a Markdown or Quarto source are prose
#'
#' Excludes fenced code blocks, chunk options, YAML front matter, display
#' math, table rows, div fences, and HTML comments, so a tell appearing in
#' code or a table is not counted as prose.
#'
#' @param lines Character vector of file lines.
#' @returns A logical vector, `TRUE` where the line is prose.
#' @export
prose_mask <- function(lines) {
  n <- length(lines)
  keep <- rep(FALSE, n)
  in_chunk <- in_yaml <- in_math <- FALSE
  for (i in seq_len(n)) {
    l <- lines[[i]]
    if (i == 1L && grepl("^---\\s*$", l)) { in_yaml <- TRUE; next }
    if (in_yaml) { if (grepl("^---\\s*$", l)) in_yaml <- FALSE; next }
    if (grepl("^\\s*```", l)) { in_chunk <- !in_chunk; next }
    if (in_chunk) next
    if (grepl("^\\s*\\$\\$", l)) { in_math <- !in_math; next }
    if (in_math) next
    if (grepl("^\\s*(#\\||\\||:::|<!--)", l)) next
    if (!nzchar(trimws(l))) next
    keep[[i]] <- TRUE
  }
  keep
}

#' Strip inline code, math, and link targets from prose
#'
#' Keeps a link's visible text, since that is prose a reader sees, but drops
#' the URL, which is not.
#'
#' @param x Character vector of prose lines.
#' @returns `x` with inline code spans, `$math$`, and link targets removed.
#' @export
strip_inline <- function(x) {
  x <- gsub("`[^`]*`", " ", x)
  x <- gsub("\\$[^$]*\\$", " ", x)
  x <- gsub("\\[([^]]*)\\]\\([^)]*\\)", "\\1", x)
  x
}

#' Scan selected lines of a file for AI tells
#'
#' @param path Path recorded on each hit, for reporting.
#' @param lines Character vector of the file's lines.
#' @param which_lines Integer line numbers to consider (typically the lines a
#'   diff added). Non-prose lines among them are dropped.
#' @returns A list with `hits` (a data frame of file, line, category, match,
#'   context, or `NULL`), `words` (prose words examined), and `examined`
#'   (prose lines examined). `words` and `examined` are reported so a caller
#'   can distinguish "no tells found" from "nothing was scanned".
#' @export
scan_lines <- function(path, lines, which_lines) {
  mask <- prose_mask(lines)
  idx <- which_lines[mask[which_lines]]
  if (length(idx) == 0L) return(list(hits = NULL, words = 0L, examined = 0L))
  txt <- strip_inline(lines[idx])

  tells <- ai_tell_patterns()
  hits <- lapply(names(tells), function(nm) {
    # gregexpr, not regexpr: a line carrying three tells is precisely the
    # clustering the catalog calls the signal, so one-per-line would hide it.
    mm <- regmatches(txt, gregexpr(tells[[nm]], txt, perl = TRUE,
                                   ignore.case = TRUE))
    k <- lengths(mm)
    if (!any(k > 0L)) return(NULL)
    j <- rep(seq_along(k), k)
    data.frame(file = path, line = idx[j], category = nm,
               match = unlist(mm), context = trimws(lines[idx[j]]),
               stringsAsFactors = FALSE)
  })
  list(hits = do.call(rbind, hits),
       words = sum(lengths(strsplit(trimws(txt), "\\s+"))),
       examined = length(idx))
}
