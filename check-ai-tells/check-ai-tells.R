#!/usr/bin/env Rscript

# Scans Markdown and Quarto prose for AI tell patterns and computes tell density.
# Supports full file scanning or diff-scoped scanning against a base ref (gha#382).

suppressPackageStartupMessages({
  # Base R only for minimal footprint and maximum speed
})

# ── Pattern Catalog ──────────────────────────────────────────────────────────

LEXICAL_TELLS <- c(
  "delve", "leverage", "utilize", "seamlessly", "seamless", "robust",
  "holistic", "nuanced", "multifaceted", "intricate", "tapestry",
  "testament", "realm", "landscape", "beacon", "plethora", "myriad",
  "pivotal", "crucial", "paramount", "underscore", "foster", "harness",
  "embark", "unlock", "elevate", "game-changer", "gamechanger",
  "cutting-edge", "state-of-the-art", "ever-evolving", "treasure trove",
  "fast-paced", "in the realm of", "at the heart of", "more than just",
  "shed light", "dive into", "dive in", "deep dive"
)

RHETORICAL_PATTERNS <- list(
  list(
    pattern = "(?i)\\b(?:it'?s|this is)\\s+not\\s+(?:just|only|merely|about)\\b",
    name = "negation-reversal antithesis"
  ),
  list(
    pattern = "(?i)\\b(?:it'?s\\s+worth\\s+noting\\s+that|it'?s\\s+important\\s+to\\s+note|it'?s\\s+essential\\s+to\\s+understand\\s+that)\\b",
    name = "signposting filler"
  )
)

# ── Prose Extraction ─────────────────────────────────────────────────────────

strip_non_prose <- function(lines) {
  # Strips YAML header, code chunks, math blocks, div blocks, and inline code/math
  in_yaml <- FALSE
  in_code_block <- FALSE
  in_math_block <- FALSE
  cleaned <- character(length(lines))

  for (i in seq_along(lines)) {
    line <- lines[i]

    # YAML front matter
    if (i == 1L && grepl("^---\\s*$", line)) {
      in_yaml <- TRUE
      cleaned[i] <- ""
      next
    }
    if (in_yaml) {
      if (grepl("^---\\s*$", line) || grepl("^\\.\\.\\.\\s*$", line)) {
        in_yaml <- FALSE
      }
      cleaned[i] <- ""
      next
    }

    # Fenced code block (``` or ~~~)
    if (grepl("^(```|~~~)", line)) {
      in_code_block <- !in_code_block
      cleaned[i] <- ""
      next
    }
    if (in_code_block) {
      cleaned[i] <- ""
      next
    }

    # Display math ($$)
    if (grepl("^\\$\\$\\s*$", line)) {
      in_math_block <- !in_math_block
      cleaned[i] <- ""
      next
    }
    if (in_math_block) {
      cleaned[i] <- ""
      next
    }

    # Div fences (::: ...)
    if (grepl("^:::\\s*", line)) {
      cleaned[i] <- ""
      next
    }

    # Strip inline code `...`
    line_clean <- gsub("`[^`]+`", " ", line)
    # Strip inline math $...$
    line_clean <- gsub("\\$[^\\$]+\\$", " ", line_clean)
    # Strip HTML tags
    line_clean <- gsub("<[^>]+>", " ", line_clean)

    cleaned[i] <- line_clean
  }

  cleaned
}

count_words <- function(lines) {
  text <- paste(lines, collapse = " ")
  words <- unlist(strsplit(text, "[[:space:][:punct:]]+"))
  length(words[nchar(words) > 0L])
}

# ── Scanner ──────────────────────────────────────────────────────────────────

scan_file_prose <- function(file_path, added_lines_only = NULL) {
  if (!file.exists(file_path)) return(NULL)
  raw_lines <- readLines(file_path, warn = FALSE)
  prose_lines <- strip_non_prose(raw_lines)
  word_count <- count_words(prose_lines)

  findings <- list()

  # Build regex for lexical tells
  lex_pattern <- paste0("(?i)\\b(", paste(LEXICAL_TELLS, collapse = "|"), ")\\b")

  lines_to_check <- if (!is.null(added_lines_only)) {
    intersect(seq_along(prose_lines), added_lines_only)
  } else {
    seq_along(prose_lines)
  }

  for (line_idx in lines_to_check) {
    line <- prose_lines[line_idx]
    if (nchar(trimws(line)) == 0L) next

    # Check lexical tells
    matches <- gregexpr(lex_pattern, line, perl = TRUE)[[1]]
    if (matches[1] != -1) {
      match_lens <- attr(matches, "match.length")
      for (k in seq_along(matches)) {
        start <- matches[k]
        len <- match_lens[k]
        val <- substr(line, start, start + len - 1L)
        findings[[length(findings) + 1L]] <- list(
          file = file_path,
          line = line_idx,
          type = "lexical",
          tell = tolower(val),
          context = trimws(line)
        )
      }
    }

    # Check rhetorical patterns
    for (rp in RHETORICAL_PATTERNS) {
      if (grepl(rp$pattern, line, perl = TRUE)) {
        findings[[length(findings) + 1L]] <- list(
          file = file_path,
          line = line_idx,
          type = "rhetorical",
          tell = rp$name,
          context = trimws(line)
        )
      }
    }
  }

  list(
    file = file_path,
    word_count = word_count,
    findings = findings
  )
}

# ── Main Entrypoint ──────────────────────────────────────────────────────────

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  
  paths_arg <- Sys.getenv("AIT_PATHS", "")
  base_ref <- Sys.getenv("AIT_BASE_REF", "")
  fail_on_high <- tolower(Sys.getenv("AIT_FAIL", "false")) %in% c("true", "1")
  threshold <- as.numeric(Sys.getenv("AIT_THRESHOLD", "10"))
  if (is.na(threshold)) threshold <- 10

  files <- if (length(args) > 0) {
    args
  } else if (nzchar(paths_arg)) {
    unlist(strsplit(paths_arg, "[,\\s]+", perl = TRUE))
  } else {
    list.files(pattern = "\\.(md|qmd|Rmd)$", recursive = TRUE, full.names = TRUE)
  }

  files <- files[file.exists(files) & !grepl("^\\./\\.git/", files)]
  if (length(files) == 0L) {
    cat("No markdown or Quarto files found to scan.\n")
    quit(status = 0)
  }

  # Diff filtering if base_ref provided
  diff_map <- list()
  if (nzchar(base_ref)) {
    diff_out <- tryCatch(
      system2("git", c("diff", "--unified=0", "--no-color", paste0(base_ref, "...HEAD")), stdout = TRUE),
      error = function(e) character(0)
    )
    if (length(diff_out) > 0) {
      cur_file <- NULL
      for (dline in diff_out) {
        if (startsWith(dline, "+++ b/")) {
          cur_file <- substr(dline, 7, nchar(dline))
          diff_map[[cur_file]] <- integer(0)
        } else if (startsWith(dline, "@@") && !is.null(cur_file)) {
          m <- regmatches(dline, regexec("\\+([0-9]+)", dline))[[1]]
          if (length(m) >= 2) {
            diff_map[[cur_file]] <- c(diff_map[[cur_file]], as.integer(m[2]))
          }
        }
      }
    }
  }

  total_words <- 0L
  all_findings <- list()

  for (f in files) {
    norm_f <- sub("^\\./", "", f)
    added_lines <- if (nzchar(base_ref) && length(diff_map) > 0) diff_map[[norm_f]] else NULL
    if (nzchar(base_ref) && is.null(added_lines) && length(diff_map) > 0) {
      # File not modified in diff
      next
    }

    res <- scan_file_prose(f, added_lines)
    if (!is.null(res)) {
      total_words <- total_words + res$word_count
      all_findings <- c(all_findings, res$findings)
    }
  }

  total_tells <- length(all_findings)
  density <- if (total_words > 0) (total_tells / total_words) * 1000 else 0

  cat(sprintf("Scanned %d file(s) (%d prose words). Found %d AI tell(s) (density: %.1f / 1000 words).\n\n",
              length(files), total_words, total_tells, density))

  if (total_tells > 0) {
    cat(sprintf("%-35s %-6s %-25s %s\n", "File", "Line", "Tell", "Snippet"))
    cat(paste(rep("-", 80), collapse = ""), "\n")
    for (item in all_findings) {
      snip <- substr(item$context, 1, 40)
      cat(sprintf("%-35s %-6d %-25s %s\n", item$file, item$line, item$tell, snip))
      cat(sprintf("::warning file=%s,line=%d::AI tell '%s' found: \"%s\"\n",
                  item$file, item$line, item$tell, snip))
    }
    cat("\n")
  }

  if (fail_on_high && density > threshold) {
    cat(sprintf("::error::AI tell density (%.1f/1000 words) exceeds threshold (%.1f/1000 words).\n",
                density, threshold))
    quit(status = 1)
  }

  quit(status = 0)
}

if (!interactive()) {
  main()
}
