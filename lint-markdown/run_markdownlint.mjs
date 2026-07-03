#!/usr/bin/env node
// Run markdownlint-cli2 over the caller repo's tracked Markdown files.
//
// Configuration (env vars, set by the composite action):
//   MARKDOWNLINT_CONFIG_FILE   Path (in the caller repo) to a markdownlint
//                              config file. Falls back to the bundled
//                              .markdownlint.default.jsonc when empty or the
//                              file does not exist.
//   MARKDOWNLINT_GLOBS         Space-separated git pathspecs of tracked files
//                              to lint (default "*.md"). Git pathspecs match
//                              at any depth, so this is recursive by default.
//   MARKDOWNLINT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
//   MARKDOWNLINT_FAIL          "true" (default) => exit 1 when markdownlint
//                              reports an error; otherwise warn (the report is
//                              still printed) but exit 0.

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileIgnores, splitList, trackedFiles } from './_pathspec.mjs';

const ACTION_DIR = dirname(fileURLToPath(import.meta.url));

function resolveConfig() {
  const override = (process.env.MARKDOWNLINT_CONFIG_FILE || '').trim();
  if (override && existsSync(override)) {
    console.log(`Using caller-provided markdownlint config: ${override}`);
    return override;
  }
  console.log('Using bundled default markdownlint config');
  return join(ACTION_DIR, '.markdownlint.default.jsonc');
}

function main() {
  const config = resolveConfig();
  const pathspecs = (process.env.MARKDOWNLINT_GLOBS || '*.md').split(/\s+/).filter(Boolean);
  const ignores = compileIgnores(splitList(process.env.MARKDOWNLINT_PATHS_IGNORE || ''));
  const fail = (process.env.MARKDOWNLINT_FAIL || 'true').trim().toLowerCase() !== 'false';

  const files = trackedFiles(pathspecs, ignores);
  if (files.length === 0) {
    console.log('No tracked Markdown files to lint.');
    return;
  }

  const cli = join(ACTION_DIR, 'node_modules', '.bin', 'markdownlint-cli2');
  const result = spawnSync(cli, ['--config', config, ...files], { stdio: 'inherit' });

  if (result.status !== 0 && !fail) {
    console.log('markdownlint reported errors above, but fail=false; continuing.');
    process.exitCode = 0;
    return;
  }
  process.exitCode = result.status ?? 1;
}

main();
