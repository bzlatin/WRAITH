'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');

test('official MCP client discovers tools, reads results and gets actionable argument errors', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wraith-context-mcp-'));
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));
  execFileSync('git', ['-C', root, 'init', '-b', 'main'], { stdio: 'pipe' });
  fs.writeFileSync(path.join(root, 'app.ts'), 'export function useful() { return 42; }\n');
  execFileSync('git', ['-C', root, 'add', '.']);
  execFileSync('git', ['-c', 'core.hooksPath=', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-C', root, 'commit', '-m', 'Fixture'], { stdio: 'pipe' });
  const client = new Client({ name: 'context-integration-test', version: '1.0.0' });
  const transport = new StdioClientTransport({ command: process.execPath,
    args: [path.resolve(__dirname, '../cli.cjs'), 'mcp', '--root', root, '--cache', path.join(root, '.cache')],
    env: { PATH: process.env.PATH }, stderr: 'pipe' });
  t.after(async () => client.close());
  await client.connect(transport);
  const listed = await client.listTools();
  assert.deepEqual(listed.tools.map(t => t.name).sort(), ['code_context', 'code_references', 'code_symbols']);
  const result = await client.callTool({ name: 'code_symbols', arguments: { query: 'useful' } });
  assert.equal(result.isError, undefined);
  assert.equal(result.structuredContent.results[0].name, 'useful');
  const invalid = await client.callTool({ name: 'code_symbols', arguments: { query: 'useful', root: '/' } });
  assert.equal(invalid.isError, true);
  const empty = await client.callTool({ name: 'code_symbols', arguments: { query: '' } });
  assert.equal(empty.isError, true);
  await client.close();
});
