#!/usr/bin/env Rscript

# Offline unit tests for description-version.R -- the pure Version:-field
# logic shared by bump-dev-version.yml and version-check.yml. Run with:
#   Rscript .github/workflows/scripts/tests/test-description-version.R

sourced <- FALSE
candidates <- c(
  ".github/workflows/scripts/description-version.R",
  "../description-version.R",
  "description-version.R"
)
for (p in candidates) {
  if (file.exists(p)) {
    source(p)
    sourced <- TRUE
    break
  }
}
if (!sourced) stop("could not locate description-version.R")

check <- function(label, actual, expected) {
  if (!identical(actual, expected)) {
    stop(sprintf(
      "FAIL: %s\n  expected: %s\n  actual:   %s",
      label, paste(expected, collapse = ","), paste(actual, collapse = ",")
    ))
  }
  cat(sprintf("ok - %s\n", label))
}

check_error <- function(label, expr) {
  ok <- tryCatch({
    force(expr)
    FALSE
  }, error = function(e) TRUE)
  if (!ok) stop(sprintf("FAIL: %s (expected an error, none raised)", label))
  cat(sprintf("ok - %s\n", label))
}

write_description <- function(version) {
  path <- tempfile(fileext = "_DESCRIPTION")
  writeLines(c(
    "Package: fixture",
    paste0("Version: ", version),
    "Title: A test fixture",
    "Description: For description-version.R's own tests."
  ), path)
  path
}

# --- read_version() ---

p1 <- write_description("0.1.0.9057")
check("read_version reads the Version: field", read_version(p1), "0.1.0.9057")

# --- versions_equal() ---

check("versions_equal: identical strings", versions_equal("0.1.0.9057", "0.1.0.9057"), TRUE)
check("versions_equal: differing dev component", versions_equal("0.1.0.9057", "0.1.0.9058"), FALSE)
check(
  "versions_equal: missing trailing component treated as zero",
  versions_equal("0.1.0", "0.1.0.0"),
  TRUE
)
check("versions_equal: differing release version", versions_equal("0.1.0", "0.2.0"), FALSE)

# --- bump_dev_version() ---

p2 <- write_description("0.1.0.9057")
r2 <- bump_dev_version(p2)
check("bump_dev_version: 4-component old", r2$old, "0.1.0.9057")
check("bump_dev_version: 4-component new (last part +1)", r2$new, "0.1.0.9058")
check("bump_dev_version: only the last component moved", read_version(p2), "0.1.0.9058")

p3 <- write_description("2.3.4.9999")
r3 <- bump_dev_version(p3)
check("bump_dev_version: carries across the boundary like a plain integer add", r3$new, "2.3.4.10000")

p4 <- write_description("0.1.0")
r4 <- bump_dev_version(p4)
check("bump_dev_version: 3-component (just-cut release) old", r4$old, "0.1.0")
check("bump_dev_version: 3-component starts a new dev cycle at .9000", r4$new, "0.1.0.9000")

p5 <- write_description("abc")
check_error("bump_dev_version: errors on a non-dotted-integer version", bump_dev_version(p5))

p6 <- write_description("1.2")
check_error("bump_dev_version: errors on a 2-component version (too few parts)", bump_dev_version(p6))

# --- version_line_index() (via read_version/bump_dev_version on a bad file) ---

p7 <- tempfile(fileext = "_DESCRIPTION")
writeLines(c("Package: fixture", "Title: no Version field at all"), p7)
check_error("read_version: errors when there is no Version: field", read_version(p7))

p8 <- tempfile(fileext = "_DESCRIPTION")
writeLines(c("Package: fixture", "Version: 0.1.0", "Version: 0.2.0"), p8)
check_error("read_version: errors when there are two Version: fields", read_version(p8))

cat("\nAll description-version tests passed.\n")
