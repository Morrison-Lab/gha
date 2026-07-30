#!/usr/bin/env Rscript

# Flag newly-added prose lines carrying the AI tells catalogued in ai-config's
# shared/writing/ai-tells.md.
#
# A thin CLI wrapper. The detectors, prose extraction, and diff parsing live in
# the {ghatools} package in this repository, so they are written, tested, and
# fixed once rather than copied into each check that needs them.
#
# Two design points worth stating here, since they explain the output shape:
#
# - **Density, not counts.** The catalog's operative sentence is "Any single
#   tell is innocent; clustering and mechanical repetition are the signal", so
#   this reports tells per 1000 prose words alongside the hits, and is
#   warn-only by default.
#
# - **Diff-scoped, always.** Only lines added since AIT_BASE_REF, via a
#   three-dot range so a moved base branch does not re-attribute other people's
#   prose. Without a base ref, or when the diff cannot be computed, the check
#   skips with a warning rather than scanning the whole tree, which would
#   reflag a corpus's entire existing prose on its first run.
#
# Environment:
#   AIT_BASE_REF      Git ref/SHA to diff against. Empty => skip.
#   AIT_GLOBS         Space-separated git pathspecs. Default "*.qmd *.md".
#   AIT_PATHS_IGNORE  Comma/newline-separated globs to skip.
#   AIT_FAIL          "true" => exit non-zero on hits. Default warn-only.
#   AIT_MAX_PER_1K    Density above which the run adds a summary annotation.

# Translate a comma/newline-separated glob list into regexes. `**` must be
# consumed before `*`, or the single-star rule would rewrite half of it first
# and leave a pattern that matches nothing.
ignore_matchers <- function(spec) {
  pats <- trimws(unlist(strsplit(spec, "[,\n]")))
  pats <- pats[nzchar(pats)]
  vapply(pats, function(p) {
    rx <- gsub("([.^$+(){}\\[\\]|\\\\])", "\\\\\\1", p)   # escape regex metas
    rx <- gsub("\\*\\*", "\001", rx)                       # placeholder for **
    rx <- gsub("\\*", "[^/]*", rx)
    rx <- gsub("\001", ".*", rx)
    rx <- gsub("\\?", ".", rx)
    paste0("^", rx, "$")
  }, character(1), USE.NAMES = FALSE)
}

is_ignored <- function(path, matchers) {
  length(matchers) > 0L && any(vapply(matchers, grepl, logical(1), x = path))
}

run_git <- function(args) {
  out <- suppressWarnings(
    system2("git", args, stdout = TRUE, stderr = FALSE)
  )
  status <- attr(out, "status")
  if (!is.null(status) && status != 0L) NULL else out
}

main <- function() {
  base <- trimws(Sys.getenv("AIT_BASE_REF", ""))
  globs <- strsplit(trimws(Sys.getenv("AIT_GLOBS", "*.qmd *.md")), "\\s+")[[1]]
  ignores <- ignore_matchers(Sys.getenv("AIT_PATHS_IGNORE", ""))
  fail <- tolower(trimws(Sys.getenv("AIT_FAIL", "false"))) == "true"
  max1k <- suppressWarnings(as.numeric(Sys.getenv("AIT_MAX_PER_1K", "3")))

  if (!nzchar(base)) {
    cat("::warning::Skipping the AI-tells check: no AIT_BASE_REF to diff",
        "against. The check is diff-scoped by design, because a whole-tree",
        "scan would reflag a corpus's entire existing prose.\n")
    return(0L)
  }

  diff <- run_git(c("diff", "--unified=0", "--no-color",
                    paste0(base, "...HEAD"), "--", globs))
  if (is.null(diff)) {
    cat("::warning::Skipping the AI-tells check: could not compute the diff",
        sprintf("against '%s' (shallow clone? unknown ref?).", base),
        "Check out with fetch-depth: 0.\n")
    return(0L)
  }

  added <- ghatools::parse_diff_added(diff)
  if (length(added) == 0L) {
    cat("No prose files changed; nothing to check.\n")
    return(0L)
  }

  all_hits <- list()
  words <- 0L
  examined <- 0L
  skipped <- 0L
  for (f in names(added)) {
    if (!file.exists(f)) next            # deleted or renamed away
    if (is_ignored(f, ignores)) { skipped <- skipped + 1L; next }
    lines <- readLines(f, warn = FALSE)
    keep <- added[[f]]
    keep <- keep[keep >= 1L & keep <= length(lines)]
    res <- ghatools::scan_lines(f, lines, keep)
    words <- words + res$words
    examined <- examined + res$examined
    if (!is.null(res$hits)) all_hits[[f]] <- res$hits
  }
  hits <- if (length(all_hits)) do.call(rbind, all_hits) else NULL
  n <- if (is.null(hits)) 0L else nrow(hits)
  per1k <- if (words > 0) 1000 * n / words else 0

  # State what was examined every run, so "0 tells" is distinguishable from a
  # run that read nothing.
  cat(sprintf(
    "Examined %d added prose line(s), %d word(s): %d tell(s), %.2f per 1k.%s\n",
    examined, words, n, per1k,
    if (skipped > 0L) sprintf(" (%d file(s) skipped by paths-ignore)", skipped) else ""
  ))

  if (n > 0L) {
    level <- if (fail) "error" else "warning"
    for (i in seq_len(n)) {
      cat(sprintf("::%s file=%s,line=%d::AI tell (%s): \"%s\" -- %s\n",
                  level, hits$file[i], hits$line[i], hits$category[i],
                  hits$match[i], substr(hits$context[i], 1, 120)))
    }
    tb <- sort(table(hits$category), decreasing = TRUE)
    cat("\nBy category: ",
        paste(sprintf("%s=%d", names(tb), as.integer(tb)), collapse = ", "),
        "\n", sep = "")
    if (!is.na(max1k) && per1k > max1k) {
      cat(sprintf(
        paste0("::%s::Density %.2f tells per 1000 added prose words exceeds ",
               "%.2f. Clustering, not any single tell, is the signal the ",
               "catalog describes.\n"),
        level, per1k, max1k
      ))
    }
  }
  if (fail && n > 0L) 1L else 0L
}

if (!interactive()) quit(status = main())
