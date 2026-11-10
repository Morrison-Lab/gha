- **The `epi204-ci.sif` recipe now installs the LaTeX packages that epi204 renders need with `tlmgr` at build time** (gha#1660).
  TinyTeX is read-only in a job, so Quarto cannot install them at render time.
  The list comes from rendering every epi204 document in both the solution and assign profiles: `koma-script`, `nameref`, `xpatch`, `colortbl`, `makecell`, `multirow`, `pdflscape`, `tabu`, `threeparttable`, `threeparttablex`, `ulem`, `varwidth`, and `wrapfig`.
  A scan of epi204's `\usepackage` lines adds `accents`, `statmath`, and `titlesec`.
