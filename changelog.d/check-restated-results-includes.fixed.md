- `check-restated-results` now follows an include the way Quarto resolves it (gha#1478).
  A path, nested or not, is resolved from the top-level page's directory, as Quarto does, and through a symlink such as sds's `sds -> .`.
  Before, every sds subfile was read as a page of its own, so the theorem that restates a solution was never seen.
  A lettered part (`-part2b`) and an exercise whose slug extends the group's (`exr-a-deviation` after `exr-a`) no longer end the search for that theorem.
  On lds, mds, pds, sds, and psw, whole-tree findings fall from 48 to 27.
