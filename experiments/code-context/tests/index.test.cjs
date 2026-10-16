'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { CodeIndex } = require('../lib/index.cjs');
const { hash } = require('../lib/repository.cjs');

function fixture(t, files) {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'wraith-context-test-'));
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }));
  const root = path.join(parent, 'repo'); fs.mkdirSync(root);
  const git = (...args) => execFileSync('git', ['-c', 'core.hooksPath=', '-c', 'user.name=Fixture',
    '-c', 'user.email=fixture@example.invalid', '-C', root, ...args], { stdio: 'pipe' }).toString();
  git('init', '-b', 'main');
  git('config', 'core.autocrlf', 'false');
  for (const [file, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
    fs.writeFileSync(path.join(root, file), text);
  }
  git('add', '.'); git('commit', '-m', 'Frozen fixture');
  return { root, parent, git, cache: path.join(parent, 'cache') };
}

test('finds actual definitions, validates source citations, and labels lexical references', t => {
  const f = fixture(t, { 'src/billing.ts': 'export function eligible(active: boolean) { return active; }\n',
    'src/use.ts': 'import { eligible } from "./billing";\nexport const canUse = eligible(true);\n',
    'src/billing.test.ts': 'test("eligible", () => expect(eligible(false)).toBe(false));\n' });
  const index = new CodeIndex(f.root, { cache: f.cache });
  const result = index.symbols('eligible');
  assert.equal(result.results.length, 1);
  assert.equal(result.results[0].path, 'src/billing.ts');
  assert.equal(result.results[0].start_line, 1);
  assert.equal(result.results[0].source_hash, hash(fs.readFileSync(path.join(f.root, 'src/billing.ts'))));
  assert.equal(result.results[0].relation, 'syntax_definition');
  const refs = index.references('eligible');
  assert.ok(refs.results.some(r => r.path === 'src/use.ts'));
  assert.equal(refs.imports['src/use.ts'][0].path, 'src/billing.ts');
  assert.equal(refs.imports['src/use.ts'][0].resolution, 'indexed_relative_source');
  assert.ok(refs.results.every(r => r.relation === 'lexical_identifier_occurrence'));
  assert.match(refs.resolution, /No complete call graph/);
  const context = index.context('eligible');
  assert.ok(context.results.some(r => r.test_candidate));
});

test('dirty edits, tracked deletion, rename and branch switch cannot serve old definitions', t => {
  const f = fixture(t, { 'src.ts': 'export const initial = 1;\n' });
  const index = new CodeIndex(f.root, { cache: f.cache });
  assert.equal(index.symbols('initial').results.length, 1);
  fs.writeFileSync(path.join(f.root, 'src.ts'), 'export const changed = 2;\n');
  assert.equal(index.symbols('initial').results.length, 0);
  assert.equal(index.symbols('changed').results.length, 1);
  fs.renameSync(path.join(f.root, 'src.ts'), path.join(f.root, 'moved.ts'));
  assert.equal(index.symbols('changed').results[0].path, 'moved.ts');
  fs.unlinkSync(path.join(f.root, 'moved.ts'));
  assert.equal(index.symbols('changed').results.length, 0);
  f.git('restore', 'src.ts'); f.git('checkout', '-b', 'other');
  fs.writeFileSync(path.join(f.root, 'src.ts'), 'export const branchOnly = 3;\n');
  f.git('add', '.'); f.git('commit', '-m', 'Other branch');
  assert.equal(index.symbols('branchOnly').results.length, 1);
  f.git('checkout', 'main');
  assert.equal(index.symbols('branchOnly').results.length, 0);
  assert.equal(index.symbols('initial').results.length, 1);
});

test('worktrees reuse syntax objects while isolating conflicting uncommitted content', t => {
  const f = fixture(t, { 'src.ts': 'export const shared = 1;\n', 'untouched.ts': 'export interface Data { value: number }\n' });
  const worktree = path.join(f.parent, 'worktree'); f.git('worktree', 'add', '-b', 'parallel', worktree);
  const a = new CodeIndex(f.root, { cache: f.cache }), b = new CodeIndex(worktree, { cache: f.cache });
  a.refresh(); const reuse = b.refresh();
  assert.equal(reuse.stats.parsed, 0); assert.equal(reuse.stats.reused, 2);
  fs.writeFileSync(path.join(f.root, 'src.ts'), 'export const primaryDirty = 1;\n');
  fs.writeFileSync(path.join(worktree, 'src.ts'), 'export const parallelDirty = 2;\n');
  const primary = a.symbols('primaryDirty'), parallel = b.symbols('parallelDirty');
  assert.equal(primary.results.length, 1); assert.equal(parallel.results.length, 1);
  assert.equal(a.symbols('parallelDirty').results.length, 0);
  assert.equal(b.symbols('primaryDirty').results.length, 0);
  assert.equal(primary.snapshot.repository_id, parallel.snapshot.repository_id);
  assert.notEqual(primary.snapshot.checkout_id, parallel.snapshot.checkout_id);
  assert.notEqual(primary.snapshot.content_hash, parallel.snapshot.content_hash);
});

test('ignored secrets, config, symlinks and nested repositories stay out of results', t => {
  const f = fixture(t, { 'safe.ts': 'export const safe = 1;\n', '.env.ts': 'const hiddenSecret = 1;',
    'secrets.ts': 'const credentialValue = 1;', 'vite.config.ts': 'const configValue = 1;',
    '.gitignore': 'ignored.ts\n' });
  fs.writeFileSync(path.join(f.root, 'ignored.ts'), 'const ignoredSecret = 1;');
  const outside = path.join(f.parent, 'outside.ts'); fs.writeFileSync(outside, 'const externalSecret = 1;');
  if (process.platform !== 'win32') fs.symlinkSync(outside, path.join(f.root, 'link.ts'));
  const nested = path.join(f.root, 'nested'); fs.mkdirSync(nested); fs.mkdirSync(path.join(nested, '.git'));
  fs.writeFileSync(path.join(nested, 'data.ts'), 'const nestedSecret = 1;');
  const index = new CodeIndex(f.root, { cache: f.cache });
  for (const name of ['hiddenSecret', 'credentialValue', 'configValue', 'ignoredSecret', 'externalSecret', 'nestedSecret']) {
    assert.equal(index.symbols(name).results.length, 0, name);
  }
  assert.equal(index.symbols('safe').results.length, 1);
});

test('a concurrent citation change produces a stale error rather than a confident old result', t => {
  const f = fixture(t, { 'src.ts': 'export const before = 1;\n' });
  const index = new CodeIndex(f.root, { cache: f.cache, beforeValidate() {
    fs.writeFileSync(path.join(f.root, 'src.ts'), 'export const after = 1;\n');
  } });
  assert.throws(() => index.symbols('before'), error => error.code === 'stale');
});

test('cache corruption is detected and reparsed; future schemas do not become empty results', t => {
  const f = fixture(t, { 'src.ts': 'export const survives = 1;\n' });
  const index = new CodeIndex(f.root, { cache: f.cache }); index.refresh();
  const object = path.join(index.cache, fs.readdirSync(index.cache).find(p => p.endsWith('.json')));
  fs.writeFileSync(object, JSON.stringify({ schema: 999, data: {} }));
  const result = index.symbols('survives');
  assert.equal(result.stats.invalid_cache, 1); assert.equal(result.results.length, 1);
  fs.writeFileSync(object, '{broken');
  assert.equal(index.symbols('survives').results.length, 1);
});

test('size limits fail the scan and retain the prior complete in-memory snapshot', t => {
  const f = fixture(t, { 'src.ts': 'export const complete = 1;\n' });
  const index = new CodeIndex(f.root, { cache: f.cache }); index.refresh();
  const previous = index.summary().snapshot.content_hash;
  fs.writeFileSync(path.join(f.root, 'oversized.ts'), 'a'.repeat(2 * 1024 * 1024 + 1));
  assert.throws(() => index.symbols('absent'), error => error.code === 'limit_exceeded');
  assert.equal(index.summary().snapshot.content_hash, previous);
});

test('context byte limits and syntax-error diagnostics remain explicit', t => {
  const f = fixture(t, { 'src.ts': 'export const broken = ;\nexport function item() { return 1; }\n',
    'other.ts': 'export function item2() { return 2; }\n' });
  const index = new CodeIndex(f.root, { cache: f.cache });
  const result = index.context('item', { limit: 1, max_bytes: 512 });
  assert.ok(result.snippet_bytes <= 512); assert.ok(result.results.length <= 1);
  assert.equal(result.syntax_error_files, 1);
  assert.throws(() => index.context('item', { max_bytes: NaN }), /max_bytes/);
  assert.throws(() => index.references('../file'), /identifier/);
  assert.throws(() => index.symbols(''), /nonempty/);
});

test('task context retains exact camel-case identifiers amid common short-name matches', t => {
  const files = { 'src/route.ts': 'export function basePath(route: string) { return route.match(/[^/]+/); }\n',
    'tests/route.test.ts': 'test("basePath handles regex parameters", () => { expect(basePath("/a")).toBe("a"); });\n' };
  for (let i = 0; i < 30; i++) files[`other/router${i}.ts`] = `export const path = "router ${i}";\n`;
  const f = fixture(t, files), index = new CodeIndex(f.root, { cache: f.cache });
  const result = index.context('basePath() must handle regex parameters with router matching');
  assert.ok(result.results.some(r => r.path === 'src/route.ts' && r.text.includes('route.match')));
  assert.ok(result.results.some(r => r.path === 'tests/route.test.ts'));
});

test('task context includes matches deep in long functions and late anonymous tests', t => {
  const filler = Array.from({ length: 100 }, (_, i) => `  const padding${i} = ${i};`).join('\n');
  const f = fixture(t, { 'src/stream.ts': `export function streamConsumer() {\n${filler}\n  return reader.read();\n}\n`,
    'tests/stream.test.ts': `${filler}\ntest("streamConsumer rejects pending reads", async () => {\n  await expect(reader.read()).rejects.toThrow();\n});\n` });
  const result = new CodeIndex(f.root, { cache: f.cache }).context('streamConsumer rejects pending reads');
  assert.ok(result.results.some(r => r.path === 'src/stream.ts' && r.text.includes('reader.read()') && r.start_line > 40));
  assert.ok(result.results.some(r => r.path === 'tests/stream.test.ts' && r.text.includes('rejects.toThrow()')));
  for (const r of result.results) {
    const lines = fs.readFileSync(path.join(f.root, r.path), 'utf8').split('\n');
    assert.equal(r.text, lines.slice(r.start_line-1, r.end_line).join('\n'));
  }
});

module.exports = { fixture };
