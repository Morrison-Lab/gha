- **`condor-batch` gives LuaLaTeX a writable TeX cache inside the container**
  ([#2012](https://github.com/Morrison-Lab/gha/issues/2012)).
  A job with an image now runs with `TEXMFVAR` and `TEXMFCACHE` under the bound `/tmp`,
  so a PDF render no longer stops with luaotfload's "no writeable cache path" on the image's read-only TeX tree.
  `condor-batch/image/build-mlg-ci.sh` passes the same variables to its test render.
