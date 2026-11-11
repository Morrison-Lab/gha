#!/usr/bin/env bash
# Fail a job in its first seconds when a self-hosted runner with a preinstalled
# toolchain lacks a command-line tool the caller lists in `apt-packages`
# (gha#1758). With `preinstalled-toolchain`, preview and quarto-publish skip
# apt, so a host without librsvg2-bin used to fail 83 seconds into the PDF pass
# with "Could not convert a SVG to a PDF for output" (lds run 42582705579).
#
# Usage: APT_PACKAGES="pkg ..." bash scripts/check-preinstalled-apt-packages.sh
#
# A package is present when dpkg lists it. A package whose command is known
# (command_for below) is also present when that command is on PATH, since a
# no-sudo host may carry the tool under ~/.local/bin.
# Only a missing tool package fails the job. Any other missing package, such as
# a -dev library from preview's default list, is a warning: it matters only for
# compiling an R package, which a preinstalled library usually makes moot, and
# failing on it would fail every Debian runner (the default list names Ubuntu's
# libnode109). With CLUSTER_RENDER=true the render runs in the cluster image, so
# a missing tool is a warning too.
# The messages name the runner ($RUNNER_NAME), so the log says which host to repair.
set -euo pipefail

# Package -> the command a render needs from it.
command_for() {
  case "$1" in
    librsvg2-bin) echo rsvg-convert ;;
    poppler-utils) echo pdftotext ;;
    ghostscript) echo gs ;;
    graphviz) echo dot ;;
    imagemagick) echo convert ;;
    *) echo "" ;;
  esac
}

runner="${RUNNER_NAME:-unknown} ($(hostname))"
missing_tools=""
missing_other=""
for pkg in ${APT_PACKAGES:-}; do
  if dpkg -s "$pkg" > /dev/null 2>&1; then
    continue
  fi
  cmd=$(command_for "$pkg")
  if [ -z "$cmd" ]; then
    missing_other="$missing_other $pkg"
  elif command -v "$cmd" > /dev/null; then
    echo "dpkg does not list $pkg, but its command $cmd is at $(command -v "$cmd")."
  else
    missing_tools="$missing_tools $pkg"
  fi
done

if [ -n "$missing_other" ]; then
  echo "::warning::Runner $runner: dpkg does not list$missing_other; the preinstalled toolchain skips apt, so a build that needs them will fail later."
fi
if [ -z "$missing_tools" ]; then
  echo "Every tool package the caller lists is present on runner $runner."
  exit 0
fi
message="Runner $runner lacks$missing_tools, and their commands are not on PATH."
if [ "${CLUSTER_RENDER:-false}" = "true" ]; then
  echo "::warning::$message The render runs in the cluster image, so continuing."
  exit 0
fi
echo "::error::$message The preinstalled toolchain skips apt, so install them on that host or route the job to a runner that has them."
exit 1
