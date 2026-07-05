#!/usr/bin/env node
// Crawl a built Quarto/HTML site with a headless browser, let MathJax finish
// typesetting each page, then scan the DOM for MathJax's own error markers.
//
// Quarto (html-math-method: mathjax) embeds raw TeX (`\(...\)`, `$$...$$`)
// unchanged in the static HTML; MathJax only parses it client-side in the
// browser. A bad equation therefore produces no warning in the Quarto/pandoc
// build log -- the static HTML is "valid" even when the embedded TeX can't be
// typeset. Only a real browser run of MathJax reveals the failure.
//
// MathJax signals a broken formula two different ways, both checked here:
//   1. A hard parse error (unmatched braces, wrong argument count, ...)
//      inserts an `[data-mjx-error]` node carrying the message.
//   2. An undefined macro (e.g. a custom command from a macro file that
//      didn't load) is NOT a hard error by default -- MathJax falls back to
//      rendering the raw, unresolved command name (e.g. "\foo") as literal
//      text. That text is colored red, but so is any legitimately
//      user-colored math (this repo's own `\red{...}` macro, for instance),
//      so color alone isn't a safe signal. A raw backslash-command name
//      surviving into the rendered text *is* safe: resolved math never
//      leaves its own TeX source behind, so a leading `\word` can only mean
//      MathJax gave up on it.
//
// A third failure mode has nothing to do with the equations themselves:
// MathJax is loaded from a CDN (<script src="...mathjax...">) rather than
// vendored, so a transient network hiccup, a blocked host, or a broken CDN
// path can keep MathJax from ever initializing on a page that references it.
// When that happens, the DOM scan above finds zero error nodes not because
// nothing was wrong, but because MathJax never ran at all -- a silent false
// pass for a check whose whole point is catching invisible-looking-fine
// breakage. checkPage() tracks this explicitly (see loadErrors below) so it
// is reported the same as a genuine equation error, rather than silently
// skipped the way a page with no MathJax script at all correctly is.

import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readdir, readFile, stat } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.ico': 'image/x-icon',
};

const MATHJAX_TIMEOUT_MS = 15_000;
const PAGE_LOAD_TIMEOUT_MS = 30_000;
const CONCURRENCY = 4;

function parseArgs(argv) {
  const args = { siteDir: '.', fail: true };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--site-dir') args.siteDir = argv[++i];
    else if (arg === '--fail') args.fail = argv[++i] !== 'false';
    else throw new Error(`Unrecognized argument: ${arg}`);
  }
  return args;
}

async function findHtmlFiles(dir, root = dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await findHtmlFiles(full, root)));
    } else if (entry.isFile() && extname(entry.name) === '.html') {
      files.push(relative(root, full));
    }
  }
  return files;
}

function startStaticServer(siteDir) {
  const server = createServer(async (req, res) => {
    try {
      const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      let filePath = join(siteDir, urlPath);
      if (urlPath.endsWith('/')) filePath = join(filePath, 'index.html');
      const body = await readFile(filePath);
      res.writeHead(200, { 'Content-Type': MIME_TYPES[extname(filePath)] || 'application/octet-stream' });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function checkPage(browser, baseUrl, relPath) {
  const page = await browser.newPage();
  try {
    await page.goto(`${baseUrl}/${relPath}`, {
      waitUntil: 'networkidle',
      timeout: PAGE_LOAD_TIMEOUT_MS,
    });

    const referencesMathJax = await page.evaluate(() =>
      Array.from(document.scripts).some((s) => /mathjax/i.test(s.src))
    );

    // A page that doesn't reference MathJax at all never defines
    // window.MathJax; skip straight to the DOM scan (there's nothing to wait
    // for, and mathJaxReady staying true is correct since nothing was expected).
    let mathJaxReady = true;
    if (referencesMathJax) {
      mathJaxReady = await page
        .waitForFunction(() => window.MathJax?.startup?.promise !== undefined, {
          timeout: MATHJAX_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    }

    let startupError = null;
    if (mathJaxReady && referencesMathJax) {
      await page
        .evaluate(() => window.MathJax.startup.promise)
        .catch((err) => {
          startupError = err.message;
        });
    }
    await page.waitForTimeout(250); // let post-promise DOM mutations (error node insertion) settle

    const domErrors = await page.evaluate(() => {
      const anchorIdOf = (node) => node.closest('[id]')?.id ?? null;

      const hardErrors = Array.from(document.querySelectorAll('[data-mjx-error]')).map((node) => ({
        anchorId: anchorIdOf(node),
        message: node.getAttribute('data-mjx-error'),
      }));

      const undefinedMacroErrors = Array.from(
        document.querySelectorAll('mjx-container mjx-mtext, mjx-container mtext')
      )
        .filter((node) => /^\\[a-zA-Z]/.test(node.textContent.trim()))
        .map((node) => ({
          anchorId: anchorIdOf(node),
          message: `undefined macro rendered as literal text: ${node.textContent.trim()}`,
        }));

      // MathJax keeps two parallel trees per formula (the visible CHTML output
      // and a hidden assistive-MathML annotation), so a single error is
      // reported by both -- dedupe on (anchor, message) before returning.
      const seen = new Set();
      return [...hardErrors, ...undefinedMacroErrors].filter(({ anchorId, message }) => {
        const key = `${anchorId} ${message}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    });

    const loadErrors = [];
    if (referencesMathJax && !mathJaxReady) {
      loadErrors.push({
        anchorId: null,
        message:
          'MathJax script referenced but never initialized (window.MathJax.startup.promise) ' +
          'before timeout -- equation rendering could not be verified on this page',
      });
    }
    if (startupError) {
      loadErrors.push({ anchorId: null, message: `MathJax startup failed: ${startupError}` });
    }

    return [...loadErrors, ...domErrors];
  } catch (err) {
    return [{ anchorId: null, message: `page failed to load: ${err.message}` }];
  } finally {
    await page.close();
  }
}

async function runWithConcurrency(items, limit, worker) {
  const results = new Array(items.length);
  let next = 0;
  async function runNext() {
    const i = next++;
    if (i >= items.length) return;
    results[i] = await worker(items[i], i);
    await runNext();
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, runNext));
  return results;
}

async function main() {
  const { siteDir, fail } = parseArgs(process.argv.slice(2));
  const siteStat = await stat(siteDir).catch(() => null);
  if (!siteStat?.isDirectory()) {
    console.error(`::error::check-equation-renders: site-dir "${siteDir}" is not a directory`);
    process.exitCode = 1;
    return;
  }

  const htmlFiles = await findHtmlFiles(siteDir);
  console.log(`check-equation-renders: found ${htmlFiles.length} HTML page(s) under ${siteDir}`);

  const server = await startStaticServer(siteDir);
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch();

  let totalErrors = 0;
  try {
    const perFileErrors = await runWithConcurrency(htmlFiles, CONCURRENCY, (relPath) =>
      checkPage(browser, baseUrl, relPath)
    );
    for (const [i, errors] of perFileErrors.entries()) {
      if (errors.length === 0) continue;
      const relPath = htmlFiles[i];
      totalErrors += errors.length;
      for (const { anchorId, message } of errors) {
        const location = anchorId ? `${relPath}#${anchorId}` : relPath;
        console.log(`::error file=${relPath}::Equation render error at ${location}: ${message}`);
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (totalErrors > 0) {
    console.log(`check-equation-renders: found ${totalErrors} equation render error(s).`);
    if (fail) process.exitCode = 1;
  } else {
    console.log('check-equation-renders: no equation render errors found.');
  }
}

main().catch((err) => {
  console.error(`::error::check-equation-renders failed: ${err.stack || err.message}`);
  process.exitCode = 1;
});
