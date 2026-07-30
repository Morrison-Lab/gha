# Adapted from d-morrison/rpt's .lintr.R. Trimmed to the rules that apply to a
# dependency-light subdirectory package: this one has no cli dependency, so the
# base-messaging bans point at rlang-free alternatives rather than cli::.
undesirable_functions <-
  lintr::default_undesirable_functions |>
  lintr::modify_defaults(
    library = paste(
      "\nuse `::` or `usethis::use_import_from()`",
      "instead of modifying the global search path.",
      "\nSee <https://r-pkgs.org/code.html#sec-code-r-landscape>."
    )
  )

lintr::linters_with_defaults(
  undesirable_function_linter(fun = undesirable_functions),
  object_usage_linter = NULL,
  line_length_linter = lintr::line_length_linter(80L)
)
