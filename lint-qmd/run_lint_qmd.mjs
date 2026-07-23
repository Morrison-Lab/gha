#!/usr/bin/env node
// Lint the prose sections of .qmd Quarto files with markdownlint.
//
// Each file is pre-processed line-by-line: Quarto code chunks
// (```{lang} / ```{=fmt} ... ```) are replaced with blank lines, preserving
// line counts so markdownlint errors map back to the correct line numbers in
// the original file. YAML front matter is left intact — markdownlint skips
// it natively.
//
// Configuration (env vars, set by the composite action):
//   LINT_QMD_CONFIG_FILE      Path (in the caller repo) to a markdownlint
//                             config file. Falls back to the bundled
//                             .markdownlint.qmd.jsonc when empty or missing.
//   LINT_QMD_GLOBS            Space-separated git pathspecs of tracked files
//                             to lint (default "*.qmd").
//   LINT_QMD_PATHS_IGNORE     Comma/newline-separated glob patterns to skip.
//   LINT_QMD_FAIL             "true" (default) => exit 1 on errors; "false"
//                             => warn but exit 0.
//   LINT_QMD_MAX_LINE_LENGTH  Integer line-length ceiling for MD013. Applied
//                             on top of the resolved config. "0" disables
//                             MD013 entirely (default "80").

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { lint, readConfig } from 'markdownlint/sync';
import { compileIgnores, splitList, trackedFiles } from './_pathspec.mjs';

// Strip `//`-style line comments from JSONC before JSON.parse. Conservative:
// handles whole-line and end-of-line comments only (no block comments), which
// is sufficient for config files where string values never contain `//`.
function parseJsonc(content) {
  return JSON.parse(content.replace(/^\s*\/\/[^\n]*/gm, '').replace(/\s+\/\/[^\n]*/g, ''));
}

const ACTION_DIR = dirname(fileURLToPath(import.meta.url));

// Replace Quarto code chunks (```{lang} / ```{=fmt} ... ```) with blank lines,
// preserving line count so markdownlint line numbers stay accurate.
// YAML front matter (--- ... ---) is left intact — markdownlint skips it
// natively. Regular display code blocks (```lang without braces) are also left
// intact; markdownlint already skips their content for most rules.
export function stripNonProse(content) {
  const lines = content.split('\n');
  const out = [];
  let inChunk = false;

  for (const line of lines) {
    if (!inChunk && /^(`{3,})\{/.test(line)) {
      inChunk = true;
      out.push('');
    } else if (inChunk && /^`{3,}\s*$/.test(line)) {
      inChunk = false;
      out.push('');
    } else if (inChunk) {
      out.push('');
    } else {
      out.push(line);
    }
  }

  return out.join('\n');
}

function resolveConfig() {
  const override = (process.env.LINT_QMD_CONFIG_FILE || '').trim();
  if (override && existsSync(override)) {
    console.log(`Using caller-provided markdownlint config: ${override}`);
    return readConfig(override, [parseJsonc]);
  }
  console.log('Using bundled default markdownlint config');
  return readConfig(join(ACTION_DIR, '.markdownlint.qmd.jsonc'), [parseJsonc]);
}

// Apply the max-line-length input on top of the resolved config.
// "0" disables MD013; any positive integer sets line_length, merging with
// any other sub-options the config already carries.
export function applyMaxLineLength(config, raw) {
  const candidate = (raw || '80').trim();
  if (!/^\d+$/.test(candidate)) {
    throw new Error(
      `Invalid max-line-length value "${candidate}". Expected a non-negative integer (0 disables MD013).`
    );
  }
  const val = Number(candidate);
  if (val === 0) {
    return { ...config, MD013: false };
  }
  const existing = config.MD013;
  return {
    ...config,
    MD013: {
      code_blocks: false,
      tables: false,
      ...(existing && typeof existing === 'object' ? existing : {}),
      line_length: val,
    },
  };
}

function formatResults(results) {
  let errorCount = 0;
  for (const [filename, errors] of Object.entries(results)) {
    for (const err of errors) {
      errorCount++;
      const rule = err.ruleNames.join('/');
      const detail = err.errorDetail ? ` [${err.errorDetail}]` : '';
      const context = err.errorContext ? ` "${err.errorContext}"` : '';
      console.log(`${filename}:${err.lineNumber}: ${rule} ${err.ruleDescription}${detail}${context}`);
    }
  }
  return errorCount;
}

function main() {
  const pathspecs = (process.env.LINT_QMD_GLOBS || '*.qmd').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.LINT_QMD_PATHS_IGNORE || ''));
  const fail = (process.env.LINT_QMD_FAIL || 'true').trim().toLowerCase() !== 'false';

  const files = trackedFiles(pathspecs, ignores);
  if (files.length === 0) {
    console.log('No tracked .qmd files to lint.');
    return;
  }

  let config = resolveConfig();
  config = applyMaxLineLength(config, process.env.LINT_QMD_MAX_LINE_LENGTH);

  const strings = Object.fromEntries(
    files.map((f) => [f, stripNonProse(readFileSync(f, 'utf8'))])
  );

  const results = lint({ strings, config });
  const errorCount = formatResults(results);

  if (errorCount === 0) {
    console.log(`No markdownlint errors in ${files.length} .qmd file(s).`);
    return;
  }

  if (fail) {
    process.exitCode = 1;
  } else {
    console.log(`\nmarkdownlint reported ${errorCount} error(s) above, but fail=false; continuing.`);
  }
}

main();
