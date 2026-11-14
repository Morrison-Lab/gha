- **`condor-batch` gives LuaLaTeX a writable TeX cache inside the container**
  ([#2012](https://github.com/Morrison-Lab/gha/issues/2012)).
  A job with an image now runs with `TEXMFVAR` and `TEXMFCACHE` set to the bound `/tmp`,
  so a PDF render no longer stops with luaotfload's "no writeable cache path" on the image's read-only TeX tree.
  They name `/tmp` itself rather than a subdirectory,
  because a render with both pointed at missing subdirectories of `/tmp` still stopped with that error.
  `condor-batch/image/build-mlg-ci.sh` passes the same variables to its test render.
- **`mlg-ci.sif` bakes the three LaTeX packages mlg's PDFs need**
  ([#2012](https://github.com/Morrison-Lab/gha/issues/2012)):
  koma-script, nameref, and xpatch,
  which Quarto cannot install at render time on the image's read-only TeX tree.
