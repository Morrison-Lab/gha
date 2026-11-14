# Installs, inside a cluster render job, the caller's `r-packages` that the
# image lacks, into the library named by the first argument (gha#2007).
# The setup steps install `r-packages` on the runner, but a cluster job runs
# in the image with its own R library, so without this a page that loads a
# package the image lacks fails on the cluster. The library sits in the
# execute node's scratch directory, as WWU CS IT asks, and is not kept.
#
# Usage: Rscript install-cluster-r-packages.R <lib> <spec-file>
# <spec-file> holds the `r-packages` input: pak-style specs separated by
# spaces, commas or newlines, split as the runner-side install splits them:
#   any::pkg, cran::pkg or pkg   CRAN package, installed when not loadable
#   deps::<path>                 the dependencies of the DESCRIPTION at <path>,
#                                checked afterwards like the other entries
#   owner/repo[@ref], github::owner/repo[@ref]
#                                GitHub package, installed when a package
#                                named like the repository is not loadable,
#                                and checked afterwards against that name
# Any other form (bioc::, url::, local::) is reported and skipped, so the
# render then fails on the missing package with R's own message.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L)
lib <- args[[1L]]
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(lib, .libPaths()))

cran_repo <- getOption("repos", c(CRAN = ""))["CRAN"]
if (is.na(cran_repo) || !nzchar(cran_repo) || identical(unname(cran_repo), "@CRAN@")) {
  options(repos = c(CRAN = "https://cloud.r-project.org"))
}

spec_lines <- readLines(args[[2L]], warn = FALSE)
spec_lines <- spec_lines[!startsWith(trimws(spec_lines), "#")]
specs <- unlist(strsplit(spec_lines, "[[:space:],]+"))
specs <- specs[nzchar(specs)]
missing_pkg <- function(pkg) !requireNamespace(pkg, quietly = TRUE)

# Sort the entries first, then install, so remotes is fetched only when a
# deps:: entry or a missing GitHub package needs it.
cran <- character()
deps <- character()
github_repos <- character()
github <- character()
for (spec in specs) {
  if (startsWith(spec, "deps::")) {
    deps <- c(deps, sub("^deps::", "", spec))
  } else if (grepl("^(any::|cran::)?[A-Za-z][A-Za-z0-9.]*$", spec)) {
    pkg <- sub("^(any::|cran::)", "", spec)
    if (missing_pkg(pkg)) cran <- c(cran, pkg)
  } else if (grepl("^(github::)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(@.+)?$", spec)) {
    repo <- sub("^github::", "", spec)
    # Strip the ref before taking the name: a ref may hold a slash.
    repo_path <- sub("@.*$", "", repo)
    pkg <- basename(repo_path)
    if (missing_pkg(pkg)) {
      github_repos <- c(github_repos, repo)
      github <- c(github, pkg)
    }
  } else {
    message("::warning::cluster render: cannot install the r-packages entry '", spec,
            "' inside the job; skipped")
  }
}
if (length(cran) > 0L) {
  message("Installing from CRAN: ", paste(cran, collapse = ", "))
  utils::install.packages(cran, lib = lib)
}
needs_remotes <- length(deps) > 0L || length(github_repos) > 0L
if (needs_remotes && missing_pkg("remotes")) {
  utils::install.packages("remotes", lib = lib)
}
deps_pkgs <- character()
for (path in deps) {
  message("Installing the dependencies of ", path)
  remotes::install_deps(path, dependencies = NA, upgrade = "never", lib = lib)
  # install_deps does not fail when a dependency cannot be installed, so its
  # packages join the check below.
  path_pkgs <- remotes::local_package_deps(path, dependencies = NA)
  deps_pkgs <- c(deps_pkgs, path_pkgs)
}
for (repo in github_repos) {
  message("Installing ", repo, " from GitHub")
  remotes::install_github(repo, upgrade = "never", lib = lib)
}
still <- Filter(missing_pkg, unique(c(cran, github, deps_pkgs)))
if (length(still) > 0L) {
  stop("cluster render: could not install ", paste(still, collapse = ", "))
}
