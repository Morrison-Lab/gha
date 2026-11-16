#!/usr/bin/env bash
# Build <repo>-ci.sif for condor-batch from a Morrison-Lab repository at a ref,
# with the one recipe every repository shares (repo-ci.def).
#
# Usage: build-repo-ci.sh <repo> [ref] [image-dir]
#   repo       Morrison-Lab repository name, such as mlg or mcsg
#   ref        branch, tag or commit to build from (default: main)
#   image-dir  directory holding lds-ci.sif and receiving <repo>-ci.sif
#              (default: /home/morri313/ci/image, the copy cf463-02 reads)
#
# What the image holds beyond the shared recipe is read from the repository,
# not from here, so a new repository needs no file in gha:
#   renv.lock                            restored into the image, when present
#   .github/ci-image/apt-packages.txt    extra apt packages, one per line
#   .github/ci-image/tlmgr-packages.txt  extra LaTeX packages, one per line
#   .github/ci-image/test.sh             run inside the new image after the
#                                        build, from the checkout; a failure,
#                                        or no test.sh, fails the build and
#                                        keeps the old image (REPO_CI_NO_TEST=1
#                                        builds without one)
#
# Run it on cf463-02 with Apptainer. A private repository needs git
# credentials for github.com. Rerun it whenever any of those files changes;
# the image is stale otherwise. A condor-batch job that lands on a CSCI
# desktop-pool head reads the image from the runner (the action's image-file
# input), which is the default image-dir. A job on a CSE cluster head reads
# /cluster/home/morri313/ci/image/<repo>-ci.sif instead, and cf463-02 cannot
# see /cluster, so copy the finished image there from a machine that mounts it.
#
# /opt/TinyTeX is read-only in a job, so Quarto cannot install a missing LaTeX
# package at render time; a test.sh that renders makes such a package fail the
# build here instead of a CI run. If it does, list the package in the
# repository's tlmgr-packages.txt and rebuild.
set -euo pipefail

repo="${1:?usage: build-repo-ci.sh <repo> [ref] [image-dir]}"
ref="${2:-main}"
image_dir="${3:-/home/morri313/ci/image}"
case "$repo" in
  *[!A-Za-z0-9._-]* | '' | .* ) echo "build-repo-ci.sh: bad repository name: $repo" >&2; exit 64 ;;
esac
# Resolve image-dir now: the script cd's into a temp directory below, where a
# relative path would no longer name it.
image_dir="$(cd "$image_dir" && pwd)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

src="$work/$repo"
git clone --quiet "https://github.com/Morrison-Lab/$repo.git" "$src"
git -C "$src" checkout --quiet "$ref"
# Only the public macros submodule, when the repository has it: renders need
# it, and the other submodules of the grading repositories (the notes) are
# private and unused by the render.
if git -C "$src" config --file .gitmodules --get submodule.latex-macros.path > /dev/null; then
  git -C "$src" submodule update --quiet --init latex-macros
fi
sha="$(git -C "$src" rev-parse HEAD)"

# The recipe's %files needs every file to exist; an empty one means none.
for pair in renv.lock:renv.lock \
            .github/ci-image/apt-packages.txt:apt-packages.txt \
            .github/ci-image/tlmgr-packages.txt:tlmgr-packages.txt; do
  from="${pair%%:*}" to="${pair##*:}"
  if [ -f "$src/$from" ]; then cp "$src/$from" "$work/$to"; else : > "$work/$to"; fi
done
cp "$here/repo-ci.def" "$work/repo-ci.def"
# The recipe bootstraps from a local lds-ci.sif, so build next to it.
cp "$image_dir/lds-ci.sif" "$work/lds-ci.sif"

cd "$work"
apptainer build "$repo-ci.sif" repo-ci.def

# Test, with the same container flags condor-batch uses.
if [ -f "$src/.github/ci-image/test.sh" ]; then
  mkdir -p "$src/.home" "$work/tmp"
  apptainer exec --containall --bind "$src:/work" --bind "$work/tmp:/tmp" \
    --pwd /work --home /work/.home --env LANG=C.UTF-8 --env TMPDIR=/tmp \
    --env TEXMFVAR=/tmp --env TEXMFCACHE=/tmp \
    "$repo-ci.sif" bash .github/ci-image/test.sh
elif [ "${REPO_CI_NO_TEST:-}" = 1 ]; then
  echo "::warning::$repo has no .github/ci-image/test.sh; REPO_CI_NO_TEST=1, so the image was not test-rendered."
else
  # Fail closed, keeping the old image: an untested image is what lets a
  # missing LaTeX package reach CI.
  echo "build-repo-ci.sh: $repo has no .github/ci-image/test.sh at $ref; add one, or set REPO_CI_NO_TEST=1." >&2
  exit 1
fi

mv "$repo-ci.sif" "$image_dir/$repo-ci.sif"
echo "Built $image_dir/$repo-ci.sif from $repo $sha"
