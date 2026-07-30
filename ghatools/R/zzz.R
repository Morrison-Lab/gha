#' @importFrom rex rex
NULL

# rex's shortcuts (`boundary`, `or`, `anything`, `maybe`, ...) are not exported
# objects -- they are names rex() resolves in its own evaluation environment.
# A script can reach them with library(rex); a package cannot, and
# `rex::boundary` errors with "not an exported object".
#
# register_shortcuts() is rex's supported mechanism for package use: it binds
# the shortcut names into this namespace so rex() calls in R/ resolve them.
# Must run at build time, hence a top-level call rather than .onLoad().
rex::register_shortcuts("ghatools")
