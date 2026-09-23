- **`preview` composite action stops repointing TinyTeX to `mirror.ctan.org`** (#907).
  Removing `tinytex::tlmgr_repo()` allows extra packages (such as `luacolor` and `lua-ul`)
  to install from TinyTeX's configured default repository rather than an unpinned redirector,
  preventing downstream PDF render failures caused by package resolution mismatches (backport to v2.0.1).
