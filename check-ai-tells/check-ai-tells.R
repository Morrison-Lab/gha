#!/usr/bin/env Rscript

# Scans Markdown and Quarto prose for AI tell patterns and computes tell density.
# Supports full file scanning or diff-scoped scanning against a base ref (gha#382).

# ── Pattern Catalog ──────────────────────────────────────────────────────────

LEXICAL_TELLS <- c(
  "delve", "leverage", "utilize", "seamlessly", "seamless", "robust",
  "holistic", "nuanced", "multifaceted", "intricate", "tapestry",
  "testament", "realm", "landscape", "beacon", "plethora", "myriad",
  "pivotal", "crucial", "paramount", "underscore", "foster", "harness",
  "embark", "unlock", "elevate", "game-changer", "gamechanger",
  "cutting-edge", "state-of-the-art", "ever-evolving", "treasure trove",
  "fast-paced", "in the realm of", "at the heart of", "more than just",
  "shed light", "dive into", "dive in", "deep dive", "actionable"
)

RHETORICAL_PATTERNS <- list(
  list(
    pattern = "(?i)\\b(?:it(?:\\s+is|'s)|this\\s+is)\\s+not\\s+(?:just|only|merely|about)\\b",
    name = "negation-reversal antithesis"
  ),
  list(
    pattern = "(?i)\\b(?:it(?:\\s+is|'s)\\s+worth\\s+noting\\s+that|it(?:\\s+is|'s)\\s+important\\s+to\\s+note|it(?:\\s+is|'s)\\s+essential\\s+to\\s+understand\\s+that)\\b",
    name = "signposting filler"
  )
)

# ── Diff Line Extraction ─────────────────────────────────────────────────────

extract_added_lines <- function(patch) {
  if (is.null(patch) || length(patch) == 0L || is.na(patch)) {
    return(integer(0))
  }
  out <- integer(0)
  new_line <- NA_integer_
  for (line in strsplit(patch, "\n", fixed = TRUE)[[1]]) {
    marker <- substr(line, 1, 1)
    if (grepl("^(diff |index |\\+\\+\\+ |--- )", line)) {
      next
    } else if (startsWith(line, "@@")) {
      matched <- regmatches(line, regexec("\\+([0-9]+)", line))[[1]]
      new_line <- as.integer(matched[2])
    } else if (marker == "+") {
      out <- c(out, new_line)
      new_line <- new_line + 1L
    } else if (marker == "-") {
      # Deleted line: no counter advance
    } else if (marker == "\\") {
      # "\ No newline at end of file"
    } else {
      # Context line
      new_line <- new_line + 1L
    }
  }
  out
}

parse_git_diff <- function(diff_lines) {
  if (length(diff_lines) == 0L) return(list())
  
  files_map <- list()
  cur_file <- NULL
  cur_patch <- character(0)

  for (line in diff_lines) {
    if (startsWith(line, "diff --git ")) {
      if (!is.null(cur_file) && length(cur_patch) > 0) {
        files_map[[cur_file]] <- extract_added_lines(paste(cur_patch, collapse = "\n"))
      }
      m <- regmatches(line, regexec("diff --git a/.+ b/(.+)$", line))[[1]]
      if (length(m) >= 2) {
        cur_file <- m[2]
      } else {
        cur_file <- NULL
      }
      cur_patch <- character(0)
    } else if (!is.null(cur_file)) {
      cur_patch <- c(cur_patch, line)
    }
  }

  if (!is.null(cur_file) && length(cur_patch) > 0) {
    files_map[[cur_file]] <- extract_added_lines(paste(cur_patch, collapse = "\n"))
  }

  files_map
}

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

  lines_to_check <- if (!is.null(added_lines_only)) {
    intersect(seq_along(prose_lines), added_lines_only)
  } else {
    seq_along(prose_lines)
  }

  # Scope word count denominator consistently with checked lines
  word_count <- if (!is.null(added_lines_only)) {
    count_words(prose_lines[lines_to_check])
  } else {
    count_words(prose_lines)
  }

  findings <- list()
  lex_pattern <- paste0("(?i)\\b(", paste(LEXICAL_TELLS, collapse = "|"), ")\\b")

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

# ── Ignore Tells Parsing ──────────────────────────────────────────────────────

MULTI_WORD_TELLS <- c(
  "negation-reversal antithesis",
  "signposting filler",
  "in the realm of",
  "at the heart of",
  "more than just",
  "shed light",
  "dive into",
  "dive in",
  "deep dive",
  "treasure trove"
)

parse_ignore_tells <- function(raw_arg) {
  if (is.null(raw_arg) || !nzchar(raw_arg)) return(character(0))
  raw_arg <- trimws(raw_arg)
  if (!nzchar(raw_arg)) return(character(0))

  lowered <- tolower(raw_arg)
  if (lowered %in% MULTI_WORD_TELLS) {
    return(lowered)
  }

  if (grepl(",", raw_arg, fixed = TRUE)) {
    tokens <- strsplit(raw_arg, ",", fixed = TRUE)[[1]]
  } else {
    tokens <- scan(text = raw_arg, what = character(), quiet = TRUE)
  }

  tokens <- tolower(trimws(tokens))
  tokens <- tokens[nzchar(tokens)]
  unname(as.character(unique(tokens)))
}

# ── Main Entrypoint ──────────────────────────────────────────────────────────

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  
  paths_arg <- Sys.getenv("AIT_PATHS", "")
  paths_ignore_arg <- Sys.getenv("AIT_PATHS_IGNORE", "")
  base_ref <- Sys.getenv("AIT_BASE_REF", "")
  ignore_tells_arg <- Sys.getenv("AIT_IGNORE_TELLS", "")
  fail_on_high <- tolower(Sys.getenv("AIT_FAIL", "false")) %in% c("true", "1")
  threshold <- as.numeric(Sys.getenv("AIT_THRESHOLD", "10"))
  if (is.na(threshold)) threshold <- 10

  ignore_tells <- parse_ignore_tells(ignore_tells_arg)

  raw_files <- if (length(args) > 0) {
    args
  } else if (nzchar(paths_arg)) {
    unlist(strsplit(paths_arg, "[,\\s]+", perl = TRUE))
  } else {
    list.files(pattern = "\\.(md|qmd|Rmd)$", recursive = TRUE, full.names = TRUE)
  }

  raw_files <- raw_files[!grepl("(^|/)\\.[^/]+", raw_files)]

  files <- unlist(lapply(raw_files, function(p) {
    if (grepl("[*?[]", p)) {
      expanded <- Sys.glob(p)
      if (length(expanded) > 0) expanded else character(0)
    } else {
      p
    }
  }))

  files <- files[file.exists(files)]

  # Apply paths-ignore if provided
  if (nzchar(paths_ignore_arg)) {
    ignore_patterns <- unlist(strsplit(paths_ignore_arg, "[,\\s]+", perl = TRUE))
    for (pat in ignore_patterns) {
      norm_pat <- sub("^\\./", "", pat)
      files <- files[!grepl(glob2rx(norm_pat), sub("^\\./", "", files)) &
                     !startsWith(sub("^\\./", "", files), norm_pat)]
    }
  }

  if (length(files) == 0L) {
    cat("No markdown or Quarto files found to scan.\n")
    quit(status = 0)
  }

  # Diff filtering if base_ref provided
  diff_map <- list()
  if (nzchar(base_ref)) {
    if (!grepl("^[a-zA-Z0-9_./@~^ -]+$", base_ref)) {
      cat(sprintf("::error::Invalid base-ref format '%s'.\n", base_ref))
      quit(status = 1)
    }
    diff_res <- tryCatch(
      system2("git", c("diff", "--unified=3", "--no-color", paste0(base_ref, "...HEAD")), stdout = TRUE, stderr = TRUE),
      error = function(e) character(0)
    )
    diff_status <- attr(diff_res, "status")
    if (!is.null(diff_status) && diff_status != 0) {
      cat(sprintf("::warning::Could not compute diff against base ref '%s'; skipping diff-scoped AI tells check.\n", base_ref))
      quit(status = 0)
    }
    diff_map <- parse_git_diff(diff_res)
    if (length(diff_map) == 0L) {
      cat(sprintf("::notice::No modified files found in diff against base ref '%s'.\n", base_ref))
      quit(status = 0)
    }
  }

  total_words <- 0L
  all_findings <- list()
  scanned_files <- 0L

  for (f in files) {
    norm_f <- sub("^\\./", "", f)
    added_lines <- if (nzchar(base_ref)) diff_map[[norm_f]] else NULL
    if (nzchar(base_ref) && is.null(added_lines)) {
      # File not touched in diff
      next
    }

    res <- scan_file_prose(f, added_lines)
    if (!is.null(res)) {
      scanned_files <- scanned_files + 1L
      total_words <- total_words + res$word_count
      all_findings <- c(all_findings, res$findings)
    }
  }

  active_findings <- list()
  suppressed_findings <- list()

  for (item in all_findings) {
    if (tolower(item$tell) %in% ignore_tells) {
      suppressed_findings[[length(suppressed_findings) + 1L]] <- item
    } else {
      active_findings[[length(active_findings) + 1L]] <- item
    }
  }

  total_tells <- length(active_findings)
  density <- if (total_words > 0) (total_tells / total_words) * 1000 else 0
  suppressed_count <- length(suppressed_findings)

  suppressed_msg <- ""
  if (suppressed_count > 0) {
    unique_ignored <- sort(unique(sapply(suppressed_findings, function(x) x$tell)))
    suppressed_msg <- sprintf(" (ignored %d tell(s) via ignore-tells: %s)",
                              suppressed_count, paste(unique_ignored, collapse = ", "))
  }

  cat(sprintf("Scanned %d file(s) (%d prose words). Found %d AI tell(s) (density: %.1f / 1000 words)%s.\n\n",
              scanned_files, total_words, total_tells, density, suppressed_msg))

  if (total_tells > 0) {
    cat(sprintf("%-35s %-6s %-25s %s\n", "File", "Line", "Tell", "Snippet"))
    cat(paste(rep("-", 80), collapse = ""), "\n")
    for (item in active_findings) {
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

# Only run main() when directly executed as top-level script, not when sourced
if (sys.nframe() == 0L) {
  main()
}
