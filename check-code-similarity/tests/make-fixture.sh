#!/usr/bin/env bash
# Generate the submission/corpus trees the `code-similarity` selftest job uses.
#
# Generated rather than committed, for the reason CLAUDE.md gives: a committed
# fixture is swept into OTHER selftest jobs' repo-wide scans -- `bib` would try
# to resolve it, `phi` would flag synthetic identifiers in it, and `typos`
# would read its prose.
#
# Layout, matching JPlag's model of a root whose CHILD directories are
# submissions:
#
#   <root>/submission/this-pr/     the code under review
#   <root>/corpus/alice/           a prior submission the PR copied
#   <root>/corpus/bob/             a prior submission it did not
#   <root>/clean-corpus/bob/       bob alone, for the no-findings case
#
# `this-pr` is alice's file with every identifier renamed: the case a diff
# would miss entirely and a token-based comparison catches.
set -euo pipefail

root="${1:?usage: make-fixture.sh <root>}"
rm -rf "$root"
# `empty-corpus` exists but holds no submission directories. That is the
# insidious case -- an artifact that did not download, a submodule that was
# not initialised -- and it must be an ERROR rather than a clean comparison.
# A merely MISSING directory is easier to catch and proves less.
mkdir -p "$root"/submission/this-pr "$root"/corpus/alice "$root"/corpus/bob \
         "$root"/clean-corpus/bob "$root"/empty-corpus

cat > "$root/corpus/alice/analysis.R" <<'EOF'
summarise_cohort <- function(data, group_var) {
  stopifnot(is.data.frame(data))
  out <- dplyr::summarise(
    dplyr::group_by(data, {{ group_var }}),
    n = dplyr::n(),
    mean_age = mean(age, na.rm = TRUE)
  )
  out[order(out$n, decreasing = TRUE), ]
}

plot_cohort <- function(summary_tbl) {
  ggplot2::ggplot(summary_tbl, ggplot2::aes(x = n, y = mean_age)) +
    ggplot2::geom_point() +
    ggplot2::theme_minimal()
}
EOF

cat > "$root/corpus/bob/model.R" <<'EOF'
fit_exposure_model <- function(df) {
  glm(outcome ~ exposure + age, data = df, family = binomial())
}

tidy_coefficients <- function(fit) {
  coefs <- summary(fit)$coefficients
  data.frame(term = rownames(coefs), estimate = coefs[, 1])
}
EOF
cp "$root/corpus/bob/model.R" "$root/clean-corpus/bob/model.R"

# alice's file with every identifier renamed and nothing else changed.
cat > "$root/submission/this-pr/analysis.R" <<'EOF'
summarize_group <- function(dataset, grouping) {
  stopifnot(is.data.frame(dataset))
  result <- dplyr::summarise(
    dplyr::group_by(dataset, {{ grouping }}),
    n = dplyr::n(),
    mean_age = mean(age, na.rm = TRUE)
  )
  result[order(result$n, decreasing = TRUE), ]
}

draw_plot <- function(tbl) {
  ggplot2::ggplot(tbl, ggplot2::aes(x = n, y = mean_age)) +
    ggplot2::geom_point() +
    ggplot2::theme_minimal()
}
EOF

echo "fixture written to $root"
