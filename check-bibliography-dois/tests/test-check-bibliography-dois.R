#!/usr/bin/env Rscript

# Unit tests for check-bibliography-dois (gha#982)

options(check_bibliography_dois.testing = TRUE)

script_dir <- tryCatch({
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    dirname(normalizePath(sub("^--file=", "", file_arg)))
  } else {
    getwd()
  }
}, error = function(e) getwd())

repo_root <- dirname(dirname(script_dir))
check_script <- file.path(repo_root, "check-bibliography-dois", "check-bibliography-dois.R")
if (!file.exists(check_script)) {
  # If run from within check-bibliography-dois/tests/
  repo_root <- dirname(dirname(normalizePath(getwd())))
  check_script <- file.path(repo_root, "check-bibliography-dois", "check-bibliography-dois.R")
}

# Find r-test-helpers.R
helpers_path <- NULL
for (p in c(
  file.path(repo_root, ".github", "workflows", "scripts", "tests", "r-test-helpers.R"),
  file.path(getwd(), ".github", "workflows", "scripts", "tests", "r-test-helpers.R"),
  file.path(getwd(), "..", "..", ".github", "workflows", "scripts", "tests", "r-test-helpers.R")
)) {
  if (file.exists(p)) {
    helpers_path <- p
    break
  }
}

if (is.null(helpers_path)) {
  stop("Could not locate r-test-helpers.R")
}

source(helpers_path)
source(check_script)

make_mock_response <- function(status_code) {
  structure(list(status_code = as.integer(status_code)), class = "response")
}

cat("Running check-bibliography-dois unit tests...\n")

# Test 1: 200 OK -> valid immediately
call_count <- 0
mock_get_200 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(200)
}
res_200 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_200)
check("200 OK is_valid", res_200$is_valid, TRUE)
check("200 OK warning is NULL", is.null(res_200$warning), TRUE)
check("200 OK error is NULL", is.null(res_200$error), TRUE)
check("200 OK call count", call_count, 1)

# Test 2: 403 Forbidden (paywalled) -> valid immediately
call_count <- 0
mock_get_403 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(403)
}
res_403 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_403)
check("403 is_valid", res_403$is_valid, TRUE)
check("403 warning is NULL", is.null(res_403$warning), TRUE)
check("403 error is NULL", is.null(res_403$error), TRUE)
check("403 call count", call_count, 1)

# Test 3: 405 Method Not Allowed -> valid immediately
call_count <- 0
mock_get_405 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(405)
}
res_405 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_405)
check("405 is_valid", res_405$is_valid, TRUE)
check("405 warning is NULL", is.null(res_405$warning), TRUE)
check("405 error is NULL", is.null(res_405$error), TRUE)
check("405 call count", call_count, 1)

# Test 4: 404 Not Found -> invalid immediately, no retry
call_count <- 0
mock_get_404 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(404)
}
res_404 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_404)
check("404 is_valid", res_404$is_valid, FALSE)
check("404 warning is NULL", is.null(res_404$warning), TRUE)
check("404 error message", res_404$error, "DOI URL returned status 404")
# One doi.org request (no retry) plus one Crossref lookup (gha#1017).
check("404 call count (no retry)", call_count, 2)

# Test 4b (gha#1017): the landing page 404s but Crossref knows the DOI ->
# valid with a not-verified warning rather than an error.
urls_seen <- character(0)
mock_get_landing_404_crossref_200 <- function(url, ...) {
  urls_seen <<- c(urls_seen, url)
  if (grepl("^https://api\\.crossref\\.org/works/", url)) {
    make_mock_response(200)
  } else {
    make_mock_response(404)
  }
}
res_landing_404 <- validate_doi_url("10.1017/9781108539890", backoff_base_sec = 0, http_get = mock_get_landing_404_crossref_200)
check("landing 404 + Crossref 200 is_valid", res_landing_404$is_valid, TRUE)
check("landing 404 + Crossref 200 error is NULL", is.null(res_landing_404$error), TRUE)
check("landing 404 + Crossref 200 warns", grepl("registered with Crossref", res_landing_404$warning), TRUE)
check("landing 404 asks Crossref for the same DOI",
      "https://api.crossref.org/works/10.1017/9781108539890" %in% urls_seen, TRUE)

# Test 4c (gha#1017): a Crossref lookup that errors is not evidence either.
mock_get_landing_404_crossref_error <- function(url, ...) {
  if (grepl("crossref", url)) stop("network down")
  make_mock_response(404)
}
res_landing_404_err <- validate_doi_url("10.1017/9781108539890", backoff_base_sec = 0, http_get = mock_get_landing_404_crossref_error)
check("landing 404 + Crossref error is_valid", res_landing_404_err$is_valid, FALSE)
check("landing 404 + Crossref error message", res_landing_404_err$error, "DOI URL returned status 404")

# Test 4d (gha#1017): only a 404 consults Crossref; a 410 still fails at once.
call_count <- 0
mock_get_410 <- function(url, ...) {
  call_count <<- call_count + 1
  make_mock_response(if (grepl("crossref", url)) 200 else 410)
}
res_410 <- validate_doi_url("10.1017/9781108539890", backoff_base_sec = 0, http_get = mock_get_410)
check("410 is_valid", res_410$is_valid, FALSE)
check("410 call count (no Crossref lookup)", call_count, 1)

# Test 5: 503 Service Unavailable on attempt 1, 200 on attempt 2 -> retries and succeeds
call_count <- 0
mock_get_503_then_200 <- function(...) {
  call_count <<- call_count + 1
  if (call_count == 1) {
    make_mock_response(503)
  } else {
    make_mock_response(200)
  }
}
res_retry_503 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_503_then_200)
check("503-then-200 is_valid", res_retry_503$is_valid, TRUE)
check("503-then-200 warning is NULL", is.null(res_retry_503$warning), TRUE)
check("503-then-200 error is NULL", is.null(res_retry_503$error), TRUE)
check("503-then-200 call count", call_count, 2)

# Test 6: 429 Too Many Requests on attempt 1, 200 on attempt 2 -> retries and succeeds
call_count <- 0
mock_get_429_then_200 <- function(...) {
  call_count <<- call_count + 1
  if (call_count == 1) {
    make_mock_response(429)
  } else {
    make_mock_response(200)
  }
}
res_retry_429 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_429_then_200)
check("429-then-200 is_valid", res_retry_429$is_valid, TRUE)
check("429-then-200 warning is NULL", is.null(res_retry_429$warning), TRUE)
check("429-then-200 error is NULL", is.null(res_retry_429$error), TRUE)
check("429-then-200 call count", call_count, 2)

# Test 7: Persistent 503 across all 3 attempts -> downgraded to warning!
call_count <- 0
mock_get_persistent_503 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(503)
}
res_persistent_503 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_persistent_503)
check("persistent 503 is_valid (downgraded to warning)", res_persistent_503$is_valid, TRUE)
check("persistent 503 error is NULL", is.null(res_persistent_503$error), TRUE)
check("persistent 503 has warning", !is.null(res_persistent_503$warning), TRUE)
check("persistent 503 warning text",
      res_persistent_503$warning,
      "DOI URL returned status 503 after 3 attempts (resolver unavailable, not verified)")
check("persistent 503 call count", call_count, 3)

# Test 8: Persistent 500 across all 3 attempts -> downgraded to warning!
call_count <- 0
mock_get_persistent_500 <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(500)
}
res_persistent_500 <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_persistent_500)
check("persistent 500 is_valid (downgraded to warning)", res_persistent_500$is_valid, TRUE)
check("persistent 500 error is NULL", is.null(res_persistent_500$error), TRUE)
check("persistent 500 has warning", !is.null(res_persistent_500$warning), TRUE)
check("persistent 500 warning text",
      res_persistent_500$warning,
      "DOI URL returned status 500 after 3 attempts (resolver unavailable, not verified)")
check("persistent 500 call count", call_count, 3)

# Test 9: Network timeout across all 3 attempts -> error
call_count <- 0
mock_get_timeout <- function(...) {
  call_count <<- call_count + 1
  stop("Connection timed out after 30 seconds")
}
res_timeout <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_timeout)
check("timeout is_valid", res_timeout$is_valid, FALSE)
check("timeout warning is NULL", is.null(res_timeout$warning), TRUE)
check("timeout has error", grepl("Connection timed out", res_timeout$error), TRUE)
check("timeout call count", call_count, 3)

# Test 10: Network error on attempt 1, 200 on attempt 2 -> retries and succeeds
call_count <- 0
mock_get_error_then_200 <- function(...) {
  call_count <<- call_count + 1
  if (call_count == 1) {
    stop("Resolving timed out")
  } else {
    make_mock_response(200)
  }
}
res_retry_error <- validate_doi_url("10.1201/9781315182780", backoff_base_sec = 0, http_get = mock_get_error_then_200)
check("error-then-200 is_valid", res_retry_error$is_valid, TRUE)
check("error-then-200 warning is NULL", is.null(res_retry_error$warning), TRUE)
check("error-then-200 error is NULL", is.null(res_retry_error$error), TRUE)
check("error-then-200 call count", call_count, 2)

# Test 11: Invalid DOI format -> immediate error, no HTTP call
call_count <- 0
mock_get_should_not_call <- function(...) {
  call_count <<- call_count + 1
  make_mock_response(200)
}
res_invalid_format <- validate_doi_url("not-a-valid-doi", backoff_base_sec = 0, http_get = mock_get_should_not_call)
check("invalid DOI format is_valid", res_invalid_format$is_valid, FALSE)
check("invalid DOI format warning is NULL", is.null(res_invalid_format$warning), TRUE)
check("invalid DOI format error", res_invalid_format$error, "Invalid DOI format: not-a-valid-doi")
check("invalid DOI format call count", call_count, 0)

# Test 12: check_doi_field checks
entry_book_with_doi <- list(CATEGORY = "book", BIBTEXKEY = "dobson4e", DOI = "10.1201/9781315182780")
check("book with DOI has_doi", check_doi_field(entry_book_with_doi)$has_doi, TRUE)

entry_book_missing_doi <- list(CATEGORY = "book", BIBTEXKEY = "dobson4e", DOI = "")
check("book missing DOI has_doi", check_doi_field(entry_book_missing_doi)$has_doi, FALSE)

entry_misc_without_doi <- list(CATEGORY = "misc", BIBTEXKEY = "misc_entry")
check("misc without DOI has_doi", check_doi_field(entry_misc_without_doi)$has_doi, TRUE)

cat("All check-bibliography-dois R unit tests passed!\n")
