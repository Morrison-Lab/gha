- **The lds CI image recipe is now in the repo, with `python3-yaml` and a baked Julia depot**
  ([#1431](https://github.com/Morrison-Lab/gha/issues/1431)).
  `condor-batch/image/lds-ci.def` is the recipe for `/cluster/home/morri313/ci/image/lds-ci.sif`.
  It now installs `python3-yaml`, so lds's pre-render no longer needs a PyYAML install,
  and it bakes RCall, Conda, and Suppressor into `/opt/julia-depot`
  (`Pkg.build("RCall")` run against `R_HOME=/usr/lib/R`),
  so JuliaCall's `install_dependency` needs no network or build at render time.
  `JULIA_DEPOT_PATH` lists the writable per-run depot first and the baked depot second.
  It also bakes the LaTeX packages the lds PDF renders needed
  (`caption`, `ctablestack`, `environ`, `fontawesome5`, `fp`, `luatexbase`, `pdfcol`, `pgf`, `tcolorbox`, `tikzfill`, `trimspaces`),
  because Quarto cannot install them at render time into the read-only `/opt/TinyTeX`.
  A PDF render in the image still needs `TEXMFVAR` and `TEXMFCACHE` under `/work`,
  or luaotfload stops with "no writeable cache path".
