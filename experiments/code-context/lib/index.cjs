'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const ts = require('typescript');
const R = require('./repository.cjs');
const SCHEMA = 1;

function parse(text, file) {
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const definitions = [], identifiers = [], imports = [];
  const visit = node => {
    if (ts.isIdentifier(node)) identifiers.push({ name: node.text, start: node.getStart(source), end: node.end });
    if (node.name && (ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node)
      || ts.isTypeAliasDeclaration(node) || ts.isEnumDeclaration(node) || ts.isVariableDeclaration(node)
      || ts.isMethodDeclaration(node) || ts.isPropertyDeclaration(node) || ts.isPropertyAssignment(node)
      || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node))) {
      const name = node.name.getText(source).replace(/^['"]|['"]$/g, '');
      const start = node.getStart(source);
      definitions.push({ name, kind: ts.SyntaxKind[node.kind], start, end: node.end });
    }
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      imports.push({ specifier: node.moduleSpecifier.text, start: node.getStart(source), end: node.end });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return { definitions, identifiers, imports, syntax_errors: source.parseDiagnostics.length };
}
function validObject(obj, text) {
  if (!obj || obj.schema !== SCHEMA || obj.typescript !== ts.version || !obj.data) return false;
  const { data } = obj;
  if (!Number.isSafeInteger(data.syntax_errors) || data.syntax_errors < 0) return false;
  for (const key of ['definitions', 'identifiers', 'imports']) {
    if (!Array.isArray(data[key]) || data[key].length > 1000000) return false;
    if (!data[key].every(v => v && typeof (v.name ?? v.specifier) === 'string'
      && Number.isSafeInteger(v.start) && Number.isSafeInteger(v.end)
      && v.start >= 0 && v.end >= v.start && v.end <= text.length)) return false;
  }
  return true;
}
function tokens(query) {
  const stop = new Set(['the', 'and', 'for', 'with', 'from', 'this', 'that', 'find', 'how', 'must',
    'its', 'into', 'only', 'while', 'rather', 'than', 'whose', 'when', 'instead', 'correctly', 'existing', 'fix']);
  // Retain an exact identifier as well as its camel-case pieces.
  const words = query + ' ' + query.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_$]/g, ' ');
  return [...new Set(words.toLowerCase().match(/[a-z0-9_$]+/g) || [])]
    .filter(t => t.length > 1 && !stop.has(t));
}
function searchWords(text) {
  // Small lexical normalization, not semantic resolution or a language model.
  return [...new Set(tokens(text).map(t => t.length > 4 ? t.replace(/(?:ing|ed|s)$/, '') : t))];
}
function lineAt(text, offset) { return text.slice(0, offset).split('\n').length; }
function options(input = {}) {
  const limit = input.limit ?? 8, max_bytes = input.max_bytes ?? 12000;
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) R.fail('invalid_arguments', 'limit must be an integer from 1 to 50.');
  if (!Number.isInteger(max_bytes) || max_bytes < 512 || max_bytes > 64000) R.fail('invalid_arguments', 'max_bytes must be an integer from 512 to 64000.');
  return { limit, max_bytes };
}
function resolvedImports(file, data, files) {
  return data.imports.slice(0, 12).map(item => {
    if (!item.specifier.startsWith('.')) return { specifier: item.specifier, path: null, resolution: 'unresolved_external_or_alias' };
    const base = path.posix.normalize(path.posix.join(path.posix.dirname(file), item.specifier));
    const stem = base.replace(/\.(?:mjs|cjs|jsx|js)$/, '');
    const choices = [base, ...['.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '/index.ts', '/index.tsx', '/index.js'].map(ext => stem + ext)];
    const target = choices.find(p => files.has(p));
    return { specifier: item.specifier, path: target || null, resolution: target ? 'indexed_relative_source' : 'unresolved_relative_source' };
  });
}

class CodeIndex {
  constructor(root, { cache = path.join(os.tmpdir(), 'wraith-code-context'), beforeValidate } = {}) {
    this.info = R.rootInfo(root);
    this.cache = path.resolve(cache, 'syntax-v1');
    fs.mkdirSync(this.cache, { recursive: true, mode: 0o700 });
    if (fs.lstatSync(this.cache).isSymbolicLink()) R.fail('invalid_cache', 'Cache directory must not be a symlink.');
    this.beforeValidate = beforeValidate;
    this.current = null;
  }
  refresh() {
    const started = performance.now(), snapshot = R.scan(this.info);
    const stats = { files: snapshot.files.size, source_bytes: snapshot.bytes, parsed: 0, reused: 0, invalid_cache: 0 };
    for (const [file, entry] of snapshot.files) {
      const key = R.hash(`${SCHEMA}:${ts.version}:${path.extname(file)}:${entry.hash}`);
      const cachePath = path.join(this.cache, key + '.json');
      let object;
      try {
        const stat = fs.lstatSync(cachePath);
        if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 32 * 1024 * 1024) throw new Error('invalid cache file');
        object = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
        if (object.source_hash !== entry.hash || !validObject(object, entry.text)) throw new Error('invalid cached syntax');
      } catch (error) {
        if (error.code !== 'ENOENT') stats.invalid_cache++;
        object = { schema: SCHEMA, typescript: ts.version, source_hash: entry.hash, data: parse(entry.text, file) };
        const temporary = path.join(this.cache, `${key}.${process.pid}.${Date.now()}.tmp`);
        try {
          fs.writeFileSync(temporary, JSON.stringify(object), { mode: 0o600, flag: 'wx' });
          fs.renameSync(temporary, cachePath);
        } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
        stats.parsed++;
      }
      if (!object || !validObject(object, entry.text)) R.fail('invalid_index', 'Syntax indexing was incomplete.');
      entry.data = object.data;
    }
    stats.reused = stats.files - stats.parsed;
    stats.elapsed_ms = Math.round((performance.now() - started) * 1000) / 1000;
    this.current = { ...snapshot, stats };
    return this.summary();
  }
  summary() {
    if (!this.current) return this.refresh();
    return { schema_version: SCHEMA, status: 'indexed', analysis_scope: 'syntax',
      snapshot: { repository_id: this.info.repository_id, checkout_id: this.info.checkout_id,
        head: this.current.head, content_hash: this.current.content_hash },
      stats: this.current.stats, excluded: this.current.excluded,
      syntax_error_files: [...this.current.files.values()].filter(v => v.data.syntax_errors).length,
      freshness: 'Files were read and hash-checked individually; this is not an atomic repository-wide filesystem snapshot.' };
  }
  validate(hits) {
    if (this.beforeValidate) this.beforeValidate();
    for (const file of new Set(hits.map(h => h.path))) {
      try {
        if (R.readSource(this.info.root, file).hash !== this.current.files.get(file).hash) {
          R.fail('stale', 'A cited file changed during the query. Retry after edits finish.');
        }
      } catch { R.fail('stale', 'A cited file changed or became unavailable during the query.'); }
    }
    if (R.git(this.info.root, ['rev-parse', 'HEAD']).trim() !== this.current.head) R.fail('stale', 'Checkout changed during the query.');
  }
  finish(candidates, input, extra = {}) {
    const { limit, max_bytes } = options(input);
    const results = [], seen = new Set();
    let used = 0, omitted = 0;
    for (const candidate of candidates) {
      const entry = this.current.files.get(candidate.path);
      const lines = entry.text.split('\n');
      const start = lineAt(entry.text, candidate.start);
      const end = Math.min(lineAt(entry.text, candidate.end), start + 39);
      const key = `${candidate.path}:${start}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const text = lines.slice(start - 1, end).join('\n');
      const bytes = Buffer.byteLength(text);
      if (results.length >= limit || used + bytes > max_bytes) { omitted++; continue; }
      used += bytes;
      results.push({ ...candidate, start_line: start, end_line: end, source_hash: entry.hash,
        text, snippet_truncated: end < lineAt(entry.text, candidate.end) });
    }
    this.validate(results);
    const imports = Object.fromEntries([...new Set(results.map(r => r.path))]
      .map(file => [file, resolvedImports(file, this.current.files.get(file).data, this.current.files)]));
    return { ...this.summary(), status: 'ok', ...extra, results, imports, omitted, snippet_bytes: used,
      limits: { ...options(input), budget_unit: 'UTF-8 snippet bytes, not model tokens or total JSON bytes' },
      resolution: 'Syntax and lexical candidates only; relative import paths resolve to indexed files. No complete call graph, type-checking or impact guarantee.' };
  }
  symbols(query, input = {}) {
    this.refresh();
    if (typeof query !== 'string' || !query.trim() || query.length > 500) R.fail('invalid_arguments', 'Use a nonempty query up to 500 characters.');
    const needle = query.toLowerCase(), candidates = [];
    for (const [file, entry] of this.current.files) for (const def of entry.data.definitions) {
      if (def.name.toLowerCase().includes(needle)) candidates.push({ path: file, ...def,
        relation: 'syntax_definition', score: def.name.toLowerCase() === needle ? 100 : 50 });
    }
    candidates.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path) || a.start - b.start);
    return this.finish(candidates, input, { query });
  }
  references(name, input = {}) {
    this.refresh();
    if (typeof name !== 'string' || !/^[$A-Z_a-z][$\w]*$/.test(name) || name.length > 200) R.fail('invalid_arguments', 'Use a single identifier.');
    const candidates = [];
    for (const [file, entry] of this.current.files) for (const occurrence of entry.data.identifiers) {
      if (occurrence.name === name) candidates.push({ path: file, ...occurrence, relation: 'lexical_identifier_occurrence' });
    }
    return this.finish(candidates, input, { query: name });
  }
  context(query, input = {}) {
    this.refresh();
    if (typeof query !== 'string' || !query.trim() || query.length > 500) R.fail('invalid_arguments', 'Use a nonempty task/query up to 500 characters.');
    const terms = searchWords(query), candidates = [];
    if (!terms.length) R.fail('invalid_arguments', 'Query needs at least one searchable word.');
    const fileWords = new Map([...this.current.files].map(([file, entry]) => [file, new Set(searchWords(file + ' ' + entry.text))]));
    const weights = new Map(terms.map(term => [term, 1 + Math.log((fileWords.size + 1)
      / (1 + [...fileWords.values()].filter(words => words.has(term)).length))]));
    const rank = (text, file) => {
      const words = searchWords(text), set = new Set(words), pathWords = new Set(searchWords(file));
      const score = terms.reduce((sum, term) => sum + weights.get(term)
        * (set.has(term) ? 1 : 0) + weights.get(term) * (pathWords.has(term) ? 0.15 : 0), 0);
      return score / (0.7 + 0.3 * Math.sqrt(Math.max(1, words.length) / 80));
    };
    for (const [file, entry] of this.current.files) {
      const test = /(?:\.(?:test|spec)\.|(?:^|\/)tests?\/)/.test(file);
      for (const def of entry.data.definitions) {
        // Long definitions are served by independently ranked windows below,
        // rather than always returning their first forty lines.
        const body = entry.text.slice(def.start, def.end);
        if (test || body.split('\n').length > 40) continue;
        const exact = terms.includes(def.name.toLowerCase()) && def.name.length > 3;
        const score = rank(body, file) + (exact ? weights.get(def.name.toLowerCase()) * 1.5 : 0);
        if (score) candidates.push({ path: file, ...def, score, relation: 'ranked_syntax_candidate', test_candidate: test });
      }
      const lines = entry.text.split('\n'), offsets = [0];
      for (const line of lines) offsets.push(offsets.at(-1) + line.length + 1);
      for (let i = 0; i < lines.length; i += 16) {
        const end = Math.min(lines.length, i + 32), body = lines.slice(i, end).join('\n');
        const scopes = entry.data.definitions.filter(d => d.start <= offsets[i] && d.end > offsets[i])
          .sort((a, b) => (a.end-a.start) - (b.end-b.start)).slice(0, 2).map(d => d.name).join(' ');
        const score = rank(scopes + ' ' + body, file);
        if (score) candidates.push({ path: file, name: test ? 'test context' : 'source context',
          kind: 'LexicalWindow', start: offsets[i], end: Math.min(entry.text.length, offsets[end] - 1),
          score, relation: test ? 'lexical_test_candidate' : 'lexical_source_candidate', test_candidate: test });
      }
    }
    candidates.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path) || a.start - b.start);
    const diverse = [];
    for (const candidate of candidates) {
      const siblings = diverse.filter(c => c.path === candidate.path);
      if (siblings.length >= 3 || siblings.some(c => Math.max(0, Math.min(c.end, candidate.end) - Math.max(c.start, candidate.start))
        > Math.min(c.end - c.start, candidate.end - candidate.start) * 0.5)) continue;
      diverse.push(candidate);
    }
    // Reserve room for a few candidate tests, without claiming coverage or relevance.
    const selected = [...diverse.filter(c => !c.test_candidate).slice(0, Math.max(1, options(input).limit - 2)),
      ...diverse.filter(c => c.test_candidate).slice(0, 2), ...diverse];
    return this.finish(selected, input, { query });
  }
}

module.exports = { CodeIndex, parse, tokens, SCHEMA };
