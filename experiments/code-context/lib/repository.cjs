'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

const EXTENSIONS = new Set(['.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs']);
const EXCLUDED = new Set(['node_modules', 'dist', 'build', 'coverage', 'vendor', 'target']);
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_TOTAL_BYTES = 128 * 1024 * 1024;
const MAX_FILES = 20000;

class ContextError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

function hash(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function fail(code, message) { throw new ContextError(code, message); }
function inside(root, file) {
  const rel = path.relative(root, file);
  return rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel);
}
function git(root, args) {
  const env = {};
  for (const name of ['PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'TMPDIR']) {
    if (process.env[name]) env[name] = process.env[name];
  }
  try {
    return execFileSync('git', ['-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=',
      '-c', 'core.pager=cat', '--no-pager', '--literal-pathspecs', '-C', root, ...args],
      { env, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, timeout: 15000,
        stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  } catch { fail('git_failed', 'Git metadata could not be read. Use an initialized local Git checkout with a commit.'); }
}
function rootInfo(input) {
  let root;
  try { root = fs.realpathSync(input); } catch { fail('invalid_root', 'Repository root does not exist.'); }
  const actual = fs.realpathSync(git(root, ['rev-parse', '--show-toplevel']).trim());
  if (actual !== root) fail('invalid_root', 'Select the Git checkout root, rather than a subdirectory.');
  const common = fs.realpathSync(path.resolve(root, git(root, ['rev-parse', '--git-common-dir']).trim()));
  return { root, repository_id: hash(common), checkout_id: hash(root) };
}
function listed(root) {
  return [...new Set(git(root, ['ls-files', '-z', '--cached', '--others', '--exclude-standard'])
    .split('\0').filter(Boolean))].filter(relative => {
      try { fs.lstatSync(path.resolve(root, relative)); return true; }
      catch (error) {
        if (error.code === 'ENOENT') return false; // A stable tracked deletion is ordinary input.
        fail('incomplete_scan', 'Checkout inventory could not be read completely.');
      }
    }).sort();
}
function eligible(file) {
  const parts = file.split('/');
  return EXTENSIONS.has(path.extname(file)) && !parts.some(p => p.startsWith('.') || EXCLUDED.has(p))
    && !/(?:^|\/)(?:secrets?|credentials?)(?:\.|\/|$)/i.test(file)
    && !/(?:^|\/)(?:[^/]+\.config|config)\.[cm]?[jt]sx?$/i.test(file);
}
function confined(root, relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0') || relative.includes('\\')) {
    fail('invalid_path', 'Use a repository-relative path with forward slashes.');
  }
  const absolute = path.resolve(root, relative);
  if (!inside(root, absolute) || absolute === root) fail('outside_root', 'Path is outside the selected checkout.');
  let current = root;
  const parts = path.relative(root, absolute).split(path.sep);
  for (let i = 0; i < parts.length; i++) {
    current = path.join(current, parts[i]);
    const stat = fs.lstatSync(current);
    if (stat.isSymbolicLink()) fail('symlink', 'Symlink paths are excluded.');
    if (i < parts.length - 1 && fs.existsSync(path.join(current, '.git'))) {
      fail('nested_repository', 'Nested repositories require their own explicit root.');
    }
  }
  if (!inside(root, fs.realpathSync(absolute))) fail('outside_root', 'Resolved path is outside the selected checkout.');
  return absolute;
}
function readSource(root, relative) {
  const absolute = confined(root, relative);
  let descriptor;
  try {
    descriptor = fs.openSync(absolute, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
    const before = fs.fstatSync(descriptor, { bigint: true });
    if (!before.isFile()) fail('not_file', 'Source path is not a regular file.');
    if (before.size > BigInt(MAX_FILE_BYTES)) fail('limit_exceeded', 'A source file exceeds the 2 MiB limit. Narrow the repository.');
    const bytes = fs.readFileSync(descriptor);
    const after = fs.fstatSync(descriptor, { bigint: true });
    const current = fs.lstatSync(confined(root, relative), { bigint: true });
    if (before.size !== after.size || before.mtimeNs !== after.mtimeNs || before.ino !== current.ino
        || before.dev !== current.dev || current.mtimeNs !== after.mtimeNs) {
      fail('stale', 'Source changed during reading. Retry after edits finish.');
    }
    if (bytes.includes(0)) fail('unsupported_source', 'A source file contains binary data.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return { text, hash: hash(bytes), bytes: bytes.length };
  } finally { if (descriptor !== undefined) fs.closeSync(descriptor); }
}
function scan(info) {
  const head = git(info.root, ['rev-parse', 'HEAD']).trim();
  const candidates = listed(info.root).filter(eligible);
  if (candidates.length > MAX_FILES) fail('limit_exceeded', 'Source file count exceeds 20,000. Narrow the repository.');
  const files = new Map();
  const excluded = { symlink_or_nested: 0 };
  let bytes = 0;
  for (const relative of candidates) {
    try {
      const entry = readSource(info.root, relative);
      bytes += entry.bytes;
      if (bytes > MAX_TOTAL_BYTES) fail('limit_exceeded', 'Source total exceeds 128 MiB. Narrow the repository.');
      files.set(relative, entry);
    } catch (error) {
      if (['symlink', 'nested_repository'].includes(error.code)) { excluded.symlink_or_nested++; continue; }
      if (error instanceof ContextError) throw error;
      fail('incomplete_scan', 'A source file could not be read completely. No new snapshot was accepted.');
    }
  }
  const again = listed(info.root).filter(eligible);
  if (JSON.stringify(candidates) !== JSON.stringify(again) || head !== git(info.root, ['rev-parse', 'HEAD']).trim()) {
    fail('stale', 'Checkout changed during scanning. Retry after edits finish.');
  }
  for (const [relative, entry] of files) {
    if (readSource(info.root, relative).hash !== entry.hash) fail('stale', 'Source changed during scanning. Retry after edits finish.');
  }
  return { files, excluded, bytes, head,
    content_hash: hash(JSON.stringify([...files].map(([p, v]) => [p, v.hash]))) };
}

module.exports = { ContextError, fail, hash, inside, git, rootInfo, listed, eligible, confined, readSource, scan };
