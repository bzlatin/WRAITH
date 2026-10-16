'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const PRODUCT = 'wraith-context';
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const exists = p => { try { fs.lstatSync(p); return true; } catch (e) { if (e.code === 'ENOENT') return false; throw e; } };
function regular(p) {
  const s = fs.lstatSync(p);
  if (!s.isFile() || s.isSymbolicLink()) throw new Error('Expected an ordinary managed file; no files were replaced.');
  return fs.readFileSync(p);
}
function directory(p) {
  if (!exists(p)) fs.mkdirSync(p, { recursive: true, mode: 0o700 });
  if (!fs.lstatSync(p).isDirectory() || fs.lstatSync(p).isSymbolicLink()) throw new Error('Installation directories must not be symlinks.');
}
function relative(name) {
  if (typeof name !== 'string' || !name || name.includes('\\') || name.includes('\0')
    || path.isAbsolute(name) || name.split('/').some(p => !p || p === '.' || p === '..')) throw new Error('Invalid package file path.');
  return name;
}
function inventory(folder, prefix = '') {
  const files = [];
  for (const name of fs.readdirSync(folder)) {
    const p = path.join(folder, name), s = fs.lstatSync(p), rel = prefix+name;
    if (s.isSymbolicLink()) throw new Error('Unexpected symlink in managed payload; preserved installation.');
    if (s.isDirectory()) files.push(...inventory(p, rel+'/'));
    else if (s.isFile()) files.push(rel);
    else throw new Error('Unexpected file in managed payload; preserved installation.');
  }
  return files.sort();
}
function locations(prefix) {
  prefix = path.resolve(prefix);
  const payload = path.join(prefix, 'lib', PRODUCT);
  const wrapper = path.join(prefix, 'bin', process.platform === 'win32' ? PRODUCT+'.cmd' : PRODUCT);
  return { prefix, payload, wrapper };
}
function defaultPrefix() {
  if (exists(path.join(__dirname, 'installation.json'))) return path.resolve(__dirname, '../..');
  return process.platform === 'win32' ? path.join(process.env.LOCALAPPDATA || os.homedir(), 'WraithContext') : path.join(os.homedir(), '.local');
}
function install(prefix, source = path.resolve(__dirname, '../dist')) {
  const manifest = JSON.parse(regular(path.join(source, 'PREVIEW-MANIFEST.json')));
  if (manifest.schema_version !== 1 || manifest.product !== PRODUCT || typeof manifest.version !== 'string'
      || !manifest.files || !Object.keys(manifest.files).length) throw new Error('Unsupported preview package. Build it first.');
  const files = Object.keys(manifest.files);
  for (const name of files) {
    relative(name);
    if (['installation.json','PREVIEW-MANIFEST.json'].includes(name) || !/^[a-f0-9]{64}$/.test(manifest.files[name])
        || digest(regular(path.join(source, name))) !== manifest.files[name]) throw new Error('Preview checksum mismatch; rebuild the package.');
  }
  for (const required of ['launcher.cjs','installer.cjs','demo.cjs','wraith-context.cjs','LICENSE','THIRD_PARTY_NOTICES.txt']) {
    if (!files.includes(required)) throw new Error('Incomplete preview package.');
  }
  directory(path.resolve(prefix));
  const loc = locations(fs.realpathSync(prefix));
  directory(path.join(loc.prefix, 'lib')); directory(path.join(loc.prefix, 'bin'));
  if (exists(loc.payload) || exists(loc.wrapper)) throw new Error('Destination already exists. Uninstall the owned preview first or choose another --prefix.');
  fs.mkdirSync(loc.payload, { mode: 0o700 });
  let wrapperCreated = false;
  try {
    for (const name of files) {
      const target = path.join(loc.payload, name);
      fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
      fs.copyFileSync(path.join(source, name), target, fs.constants.COPYFILE_EXCL);
      fs.chmodSync(target, name === 'launcher.cjs' ? 0o755 : 0o600);
      if (digest(regular(target)) !== manifest.files[name]) throw new Error('Package changed during installation.');
    }
    let wrapperRecord;
    const launcher = path.join(loc.payload,'launcher.cjs');
    let text;
    if (process.platform === 'win32') {
      if (/[\r\n%!]/.test(process.execPath+launcher)) throw new Error('Use an installation and Node path without command-expansion characters.');
      text = '@echo off\r\n"'+process.execPath+'" "'+launcher+'" %*\r\n';
    } else {
      const quote = s => "'"+s.replace(/'/g,"'\\''")+"'";
      text = '#!/bin/sh\nexec '+quote(process.execPath)+' '+quote(launcher)+' "$@"\n';
    }
    fs.writeFileSync(loc.wrapper,text,{flag:'wx',mode:0o755});
    wrapperRecord = { kind:'file', sha256:digest(text) };
    wrapperCreated = true;
    fs.writeFileSync(path.join(loc.payload, 'installation.json'), JSON.stringify({ schema_version:1, product:PRODUCT,
      version:manifest.version, prefix:loc.prefix, files:manifest.files, wrapper:wrapperRecord }, null, 2)+'\n', { flag:'wx', mode:0o600 });
    return { status:'installed', version:manifest.version, command:loc.wrapper, prefix:loc.prefix };
  } catch (error) {
    if (wrapperCreated) fs.unlinkSync(loc.wrapper);
    fs.rmSync(loc.payload, { recursive:true, force:true });
    throw error;
  }
}
function uninstall(prefix) {
  const loc = locations(prefix);
  // Refuse redirection through prefix/lib/bin or a replaced installation directory.
  for (const p of [loc.prefix, path.join(loc.prefix,'lib'), path.join(loc.prefix,'bin'), loc.payload]) {
    const s = fs.lstatSync(p);
    if (!s.isDirectory() || s.isSymbolicLink()) throw new Error('Installation directory changed; nothing was removed.');
  }
  const meta = JSON.parse(regular(path.join(loc.payload, 'installation.json')));
  if (meta.schema_version !== 1 || meta.product !== PRODUCT || meta.prefix !== fs.realpathSync(loc.prefix)
      || !meta.files || !meta.wrapper) throw new Error('Unrecognized installation; nothing was removed.');
  const files = Object.keys(meta.files).map(relative).sort();
  if (JSON.stringify(inventory(loc.payload)) !== JSON.stringify([...files,'installation.json'].sort())) {
    throw new Error('Installation has extra files; preserve them before uninstalling. Nothing was removed.');
  }
  for (const name of files) {
    if (digest(regular(path.join(loc.payload,name))) !== meta.files[name]) throw new Error('An installed file changed; nothing was removed.');
  }
  const s = fs.lstatSync(loc.wrapper);
  if (meta.wrapper.kind === 'symlink') {
    if (!s.isSymbolicLink() || meta.wrapper.target !== '../lib/'+PRODUCT+'/launcher.cjs'
        || fs.readlinkSync(loc.wrapper) !== meta.wrapper.target) throw new Error('Command link changed; nothing was removed.');
  } else if (meta.wrapper.kind !== 'file' || digest(regular(loc.wrapper)) !== meta.wrapper.sha256) {
    throw new Error('Command file changed; nothing was removed.');
  }
  fs.unlinkSync(loc.wrapper);
  fs.rmSync(loc.payload, { recursive:true });
  return { status:'uninstalled', retained:'Repository, demo directories, syntax caches and agent configuration were retained.' };
}
function main(argv) {
  const args = [...argv], operation = args[0] === 'uninstall' ? args.shift() : 'install';
  let prefix = defaultPrefix();
  if (args.length) {
    if (args.length !== 2 || args[0] !== '--prefix' || !args[1]) throw new Error('Usage: installer.cjs [uninstall] [--prefix PATH]');
    prefix = path.resolve(args[1]);
  }
  const result = operation === 'install' ? install(prefix) : uninstall(prefix);
  console.log(JSON.stringify(result, null, 2));
  if (operation === 'install') console.log('Add the command directory to PATH yourself, or use the full command path printed above.');
}
module.exports = { install, uninstall, main, digest, defaultPrefix };
if (require.main === module) {
  try { main(process.argv.slice(2)); } catch (e) { console.error(e.message); process.exitCode = 2; }
}
