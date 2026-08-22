import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import assert from 'node:assert';

const testDir = join(process.cwd(), 'lint-markdown', 'tests', 'temp_table_fixture');
const scriptPath = join(process.cwd(), 'lint-markdown', 'check_table_splits.mjs');

// Run the checker over one fixture file. Returns { failed, stdout }.
function run(file, env = {}) {
  try {
    return {
      failed: false,
      stdout: execFileSync('node', [scriptPath], {
        env: { ...process.env, MARKDOWNLINT_GLOBS: file, ...env },
        encoding: 'utf8',
      }),
    };
  } catch (err) {
    return { failed: true, stdout: err.stdout || '' };
  }
}

function fixture(name, content) {
  const path = join(testDir, name);
  writeFileSync(path, content);
  return path;
}

try {
  mkdirSync(testDir, { recursive: true });

  // 1. Positive control: the README.md shape this check exists for (#558) --
  //    a table whose rows continue after a blank line with no delimiter row.
  const split = fixture('split.md', `# Fixture

| Workflow | Purpose |
|---|---|
| \`check-ai-tells.yml\` | Scan prose for AI tells |
| \`check-phi.yml\` | Scan for PHI |

| \`check-secrets.yml\` | Scan history for credentials |
| \`check-links.yml\` | lychee link check |
`);

  let res = run(split);
  assert.strictEqual(res.failed, true, 'Expected a split table to fail the check');
  assert.match(res.stdout, /Found 1 split GFM table/);
  assert.match(res.stdout, /split\.md,line=8/);
  assert.match(res.stdout, /block of 2 row\(s\)/);

  // 2. Positive control: the other split shape -- a blank line between the
  //    header row and its delimiter row, which leaves neither block a table.
  const headerSplit = fixture('header-split.md', `# Fixture

| Workflow | Purpose |

|---|---|
| \`check-phi.yml\` | Scan for PHI |
`);

  res = run(headerSplit);
  assert.strictEqual(res.failed, true, 'Expected a header/delimiter split to fail the check');
  assert.match(res.stdout, /Found 2 split GFM table/);

  // 3. Negative control: two deliberately adjacent tables. This is the case
  //    the crude "blank line between two pipe lines" scan gets wrong -- the
  //    second block has its own delimiter row, so both are real tables.
  const twoTables = fixture('two-tables.md', `# Fixture

| Input | Default |
|---|---|
| \`fail\` | \`true\` |

| Output | Meaning |
|---|---|
| \`kind\` | The failure class |
`);

  res = run(twoTables);
  assert.strictEqual(res.failed, false, 'Two adjacent valid tables must not be flagged');
  assert.match(res.stdout, /No split GFM tables found/);

  // 4. Negative control: pipe rows inside a fenced code block, including a
  //    split one. A fence is literal content, not a table.
  const fenced = fixture('fenced.md', `# Fixture

\`\`\`markdown
| Workflow | Purpose |
|---|---|
| \`a.yml\` | first |

| \`b.yml\` | second |
\`\`\`

Ordinary prose.
`);

  res = run(fenced);
  assert.strictEqual(res.failed, false, 'Pipe rows inside a fence must not be flagged');

  // 5. Negative control: an isolated pipe-prefixed prose line, with no pipe
  //    block adjacent to it. The neighbour requirement is what keeps this
  //    check from firing on stray pipes.
  const lone = fixture('lone.md', `# Fixture

Some prose about shell pipelines.

| this line begins with a pipe but is not part of any table

More prose.
`);

  res = run(lone);
  assert.strictEqual(res.failed, false, 'A lone pipe-prefixed line must not be flagged');

  // 6. Negative control: four-space-indented pipe lines are an indented code
  //    block, not a table, so a blank line between them is not a split.
  const indented = fixture('indented.md', `# Fixture

Example markup:

    | Workflow | Purpose |
    |---|---|

    | \`a.yml\` | first |

Done.
`);

  res = run(indented);
  assert.strictEqual(res.failed, false, 'Four-space-indented pipe lines must not be flagged');

  // --- Cases from the cross-vendor (codex) review of #576. Each reproduced a
  // --- real defect before the detection rule was rewritten.

  // 9. A tilde fence whose content includes a same-character run followed by
  //    text. GFM lets only whitespace follow a CLOSING fence, so this line is
  //    content; matching openers and closers with one pattern ended the block
  //    early and exposed the code inside it to the scan.
  const fenceTrailing = fixture('fence-trailing.md', `# Fixture

~~~markdown
~~~ not a closing fence
| A | B |
|---|---|
| x | y |

| z | w |
~~~

Prose.
`);

  res = run(fenceTrailing);
  assert.strictEqual(res.failed, false, 'A run followed by text must not close a fence');

  // 10. A GFM table whose delimiter row omits its outer pipes, followed by an
  //     unrelated table. GFM makes outer pipes optional on any row, so this is
  //     one valid table; requiring a leading pipe on every row split it and
  //     reported its own body as an orphan.
  const mixedPipes = fixture('mixed-pipes.md', `# Fixture

| A | B |
--- | ---
| x | y |

| C | D |
|---|---|
| 1 | 2 |
`);

  res = run(mixedPipes);
  assert.strictEqual(res.failed, false, 'A delimiter row without outer pipes must not split the table');

  //     The case above passes with or without the outer-pipe fix, because the
  //     merge test alone already keeps it quiet -- so it is kept as a guard
  //     rather than as proof. THIS is the discriminating case: the same table
  //     genuinely split, which is a false NEGATIVE unless the pipe-less
  //     delimiter row is recognized as part of the table.
  const mixedPipesSplit = fixture('mixed-pipes-split.md', `# Fixture

| A | B |
--- | ---
| x | y |

| z | w |
`);

  res = run(mixedPipesSplit);
  assert.strictEqual(res.failed, true, 'A split of a table with a pipe-less delimiter row must be caught');
  assert.match(res.stdout, /Found 1 split GFM table/);

  // 11. A header and delimiter disagreeing on cell count is not a table at all
  //     per GFM, so it must not be credited as one.
  const widthMismatch = fixture('width-mismatch.md', `# Fixture

| A | B |
|---|---|
| 1 | 2 |

| C | D |
|---|
| E |
`);

  res = run(widthMismatch);
  assert.strictEqual(res.failed, false, 'A header/delimiter width mismatch is not a split table');

  //     That case is quiet with or without the width-equality check, so it is
  //     a guard rather than proof. The discriminating case is a MERGED pair
  //     whose header and delimiter disagree: GFM recognizes no table there, so
  //     there is no table to have been split, and crediting it as one reports
  //     an ordinary paragraph as a defect.
  const mergedWidthMismatch = fixture('merged-width-mismatch.md', `# Fixture

| X |
|---|---|

| 1 | 2 |
`);

  res = run(mergedWidthMismatch);
  assert.strictEqual(res.failed, false, 'A merged header/delimiter width mismatch must not be flagged');

  // 12. A real table followed by an unrelated pipe-prefixed literal line.
  //     Merging anything onto a real table still parses as a table, so the
  //     width test is what keeps this quiet.
  const literalAfterTable = fixture('literal-after-table.md', `# Fixture

| A | B | C |
|---|---|---|
| 1 | 2 | 3 |

| a single pipe-prefixed literal line
`);

  res = run(literalAfterTable);
  assert.strictEqual(res.failed, false, 'A literal pipe line after a table must not be flagged');

  // 13. Two unrelated pipe-prefixed paragraphs, neither a table. Without the
  //     merge test these were reported as a split of each other.
  const twoLiterals = fixture('two-literals.md', `# Fixture

| first alternative

| second alternative
`);

  res = run(twoLiterals);
  assert.strictEqual(res.failed, false, 'Two literal pipe paragraphs must not be flagged');

  // 14. An unclosed fence swallows the rest of the file, so a split inside it
  //     is code rather than a defect.
  const unclosed = fixture('unclosed.md', `# Fixture

\`\`\`text
| A | B |
|---|---|
| 1 | 2 |

| 3 | 4 |
`);

  res = run(unclosed);
  assert.strictEqual(res.failed, false, 'An unclosed fence must swallow the rest of the file');

  // 15. A longer closer legitimately closes a shorter fence, so a split AFTER
  //     the block is still a real finding.
  const longerCloser = fixture('longer-closer.md', `# Fixture

\`\`\`text
not markdown
\`\`\`\`

| A | B |
|---|---|
| 1 | 2 |

| 3 | 4 |
`);

  res = run(longerCloser);
  assert.strictEqual(res.failed, true, 'A longer closer must close the fence, exposing a later split');
  assert.match(res.stdout, /Found 1 split GFM table/);

  // --- From the Claude review of #576, round 2. Both directions of the merge
  // --- must be tried: an unrelated pipe block above the header half of a
  // --- split makes the `previous` merge fail, and committing to it means the
  // --- `next` merge that would have validated is never tried.

  // 16. Under-report: the lower half still self-reports via its own previous
  //     merge, so the split is found but the header half is missed.
  const strayAbove = fixture('stray-above.md', `# Fixture

| stray

| A | B |

|---|---|
| 1 | 2 |
`);

  res = run(strayAbove);
  assert.strictEqual(res.failed, true, 'A split below a stray pipe block must be caught');
  assert.match(res.stdout, /Found 2 split GFM table/);

  // 17. Total miss: widen a trailing row so the lower half cannot validate
  //     either, and the whole split disappears unless both directions are tried.
  const strayAboveTotalMiss = fixture('stray-above-total-miss.md', `# Fixture

| stray

| A | B |

|---|---|
| 1 | 2 | 3 |
`);

  res = run(strayAboveTotalMiss);
  assert.strictEqual(res.failed, true, 'A split whose lower half cannot self-report must still be caught');
  assert.match(res.stdout, /Found 1 split GFM table/);

  // 7. The fail input downgrades a finding to a warning: same report, exit 0.
  res = run(split, { TABLE_SPLIT_FAIL: 'false' });
  assert.strictEqual(res.failed, false, 'TABLE_SPLIT_FAIL=false must not fail the check');
  assert.match(res.stdout, /Found 1 split GFM table/);

  // 8. paths-ignore skips a file that would otherwise be flagged.
  res = run(split, { TABLE_SPLIT_PATHS_IGNORE: '**/temp_table_fixture/**' });
  assert.strictEqual(res.failed, false, 'An ignored path must not be flagged');
  assert.match(res.stdout, /No split GFM tables found/);

  console.log('✓ All split-table tests passed!');
} finally {
  rmSync(testDir, { recursive: true, force: true });
}
