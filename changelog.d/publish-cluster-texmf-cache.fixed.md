- `quarto-publish`'s cluster render (`cluster-render: true`) now points
  `TEXMFVAR` and `TEXMFCACHE` at a `.texvar` directory under the checkout,
  as the preview's cluster render already does,
  so a PDF render no longer fails with luaotfload's
  "no writeable cache path" (Morrison-Lab/epi202#28).
