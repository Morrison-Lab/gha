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
