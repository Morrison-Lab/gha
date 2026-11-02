- `check-one-div-per-subfile` no longer counts a `.content-hidden` or `.content-visible` wrapper whose only divs are proofs or solutions as a second top-level div.
  That wrapper is how the lab hides a proof from slides, so every touched theorem subfile with a hidden proof failed (Morrison-Lab/mcs#48).
