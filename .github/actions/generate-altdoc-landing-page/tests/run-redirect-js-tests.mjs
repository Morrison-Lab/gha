// Execute the 404 page's redirect script against a table of request paths.
//
// The Python tests next to this file can only assert that the mapping and base
// path reach the page as text. Whether the script then sends a given request
// to the right place is a different question, and getting it wrong is silent:
// a bad redirect still renders a plausible-looking not-found page. So run the
// real script with a stubbed `window` and check where each path lands.
//
// Usage: node run-redirect-js-tests.mjs <path-to-404.html>

import { readFileSync } from "node:fs";

const pagePath = process.argv[2];
if (!pagePath) {
  console.error("usage: node run-redirect-js-tests.mjs <path-to-404.html>");
  process.exit(1);
}

const page = readFileSync(pagePath, "utf8");
const match = page.match(/<script>([\s\S]*?)<\/script>/);
if (!match) {
  console.error(`no <script> block found in ${pagePath}`);
  process.exit(1);
}
const script = match[1];

// `null` means the script should leave the request alone and let the
// not-found page render.
const cases = [
  ["/serocalculator/main/", "/serocalculator/dev/"],
  ["/serocalculator/main", "/serocalculator/dev/"],
  ["/serocalculator/main/reference/index.html", "/serocalculator/dev/reference/index.html"],
  ["/serocalculator/master/articles/intro.html", "/serocalculator/dev/articles/intro.html"],
  // Pattern-and-template and exact mappings:
  // reference/index.html=latest-tag/reference.html (exact key takes precedence over prefix)
  ["/serocalculator/reference/index.html", "/serocalculator/latest-tag/reference.html"],
  // reference/*=latest-tag/man/* (wildcard remainder is substituted)
  ["/serocalculator/reference/est_seroincidence.html", "/serocalculator/latest-tag/man/est_seroincidence.html"],
  // articles/*=latest-tag/vignettes/articles/*
  ["/serocalculator/articles/intro.html", "/serocalculator/latest-tag/vignettes/articles/intro.html"],
  // news/index.html=latest-tag/news.html (exact key)
  ["/serocalculator/news/index.html", "/serocalculator/latest-tag/news.html"],
  // news/other.html has no wildcard mapping, so it must not redirect
  ["/serocalculator/news/other.html", null],
  // Empty remainder on wildcard mapping
  ["/serocalculator/reference/", "/serocalculator/latest-tag/man/"],
  ["/serocalculator/reference", "/serocalculator/latest-tag/man/"],
  // Outside prefix boundaries
  ["/serocalculator/reference_extra/index.html", null],
  ["/serocalculator/man/est_seroincidence.html", null],
  ["/serocalculator/vignettes/articles/intro.html", null],
  // Already on the current layout: a genuinely missing page must not redirect,
  // or a typo'd /dev/ URL would bounce forever.
  ["/serocalculator/dev/nope.html", null],
  ["/serocalculator/latest-tag/nope.html", null],
  // A version directory that merely starts with a mapped name is not a match.
  ["/serocalculator/maintenance/index.html", null],
  // Outside the project site's base path.
  ["/other-repo/main/index.html", null],
  ["/", null],
];

// Query strings and fragments have to survive the rewrite, or a deep link into
// a specific section lands at the top of the page instead.
const preserveCases = [
  ["/serocalculator/main/reference/index.html", "?q=1", "#est_seroincidence",
   "/serocalculator/dev/reference/index.html?q=1#est_seroincidence"],
  ["/serocalculator/reference/index.html", "?topic=sero", "#equations",
   "/serocalculator/latest-tag/reference.html?topic=sero#equations"],
  ["/serocalculator/reference/est_seroincidence.html", "?q=abc", "#fig1",
   "/serocalculator/latest-tag/man/est_seroincidence.html?q=abc#fig1"],
];

let failures = 0;

function run(pathname, search, hash) {
  let replacedWith = null;
  const window = {
    location: {
      pathname,
      search,
      hash,
      replace(url) {
        replacedWith = url;
      },
    },
  };
  new Function("window", script)(window);
  return replacedWith;
}

for (const [pathname, expected] of cases) {
  const actual = run(pathname, "", "");
  if (actual !== expected) {
    console.error(
      `FAIL ${pathname}\n  expected: ${expected === null ? "(no redirect)" : expected}\n  actual:   ${actual === null ? "(no redirect)" : actual}`,
    );
    failures += 1;
  }
}

for (const [pathname, search, hash, expected] of preserveCases) {
  const actual = run(pathname, search, hash);
  if (actual !== expected) {
    console.error(
      `FAIL ${pathname}${search}${hash}\n  expected: ${expected}\n  actual:   ${actual === null ? "(no redirect)" : actual}`,
    );
    failures += 1;
  }
}

const total = cases.length + preserveCases.length;
if (failures > 0) {
  console.error(`${failures}/${total} redirect cases failed`);
  process.exit(1);
}
console.log(`all ${total} redirect cases passed`);
