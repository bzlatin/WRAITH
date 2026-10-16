'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { install, uninstall, digest } = require('../preview/installer.cjs');
const root = path.resolve(__dirname,'..');
execFileSync(process.execPath,[path.join(root,'scripts/build.cjs')],{cwd:root,stdio:'pipe'});
function temporary(t) {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(),'wraith-preview-'));
  t.after(()=>fs.rmSync(folder,{recursive:true,force:true}));
  return folder;
}
function fakePackage(folder) {
  const source = path.join(folder,'package'); fs.mkdirSync(source);
  const files = {};
  for (const name of ['launcher.cjs','installer.cjs','demo.cjs','wraith-context.cjs','LICENSE','THIRD_PARTY_NOTICES.txt']) {
    fs.writeFileSync(path.join(source,name),name);files[name]=digest(name);
  }
  fs.writeFileSync(path.join(source,'PREVIEW-MANIFEST.json'),JSON.stringify({schema_version:1,product:'wraith-context',version:'test',files}));
  return source;
}

test('installed standalone preview creates a working demo and connects through MCP', async t => {
  const folder = temporary(t), prefix = path.join(folder,"home with spaces '"), installed = install(prefix);
  const launcher = path.join(prefix,'lib/wraith-context/launcher.cjs');
  const cli = (...args) => execFileSync(process.execPath,[launcher,...args],{encoding:'utf8',stdio:['ignore','pipe','pipe']});
  assert.equal(cli('--preview-version').trim(),'0.1.0-preview.1');
  assert.match(cli('--help'),/Preview helpers/);
  if (process.platform !== 'win32') assert.match(execFileSync(installed.command,['--help'],{encoding:'utf8'}),/Core commands/);
  const demo = path.join(folder,'demo');
  const result = JSON.parse(cli('demo','--directory',demo));
  assert.equal(result.tests_passed,true);
  for (const file of ['src/auth/permissions.ts','src/api/projects.ts','tests/access.test.mjs']) assert.ok(result.cited_files.includes(file));
  const original = fs.readFileSync(path.join(demo,'src/auth/permissions.ts'),'utf8');
  assert.throws(()=>cli('demo','--directory',demo));
  assert.equal(fs.readFileSync(path.join(demo,'src/auth/permissions.ts'),'utf8'),original);
  const config = cli('codex-config','--root',demo);
  assert.ok(!config.includes('node_modules'));
  assert.ok(!config.includes('approval_mode'));
  const unattended = cli('codex-config','--root',demo,'--allow-read-tools');
  assert.equal((unattended.match(/approval_mode = "auto"/g)||[]).length,3);
  for (const name of ['code_context','code_symbols','code_references']) assert.ok(unattended.includes('[mcp_servers.wraith_context.tools.'+name+']'));
  assert.ok(!unattended.includes('default_tools_approval_mode'));
  assert.ok(!unattended.includes('approval_policy'));
  assert.throws(()=>cli('codex-config','--root',demo,'--allow-read-tools','--allow-read-tools'));
  const command = JSON.parse(config.split('\n').find(l=>l.startsWith('command = ')).slice(10));
  const args = JSON.parse(config.split('\n').find(l=>l.startsWith('args = ')).slice(7));
  const client = new Client({name:'preview-test',version:'1'});
  t.after(()=>client.close());
  await client.connect(new StdioClientTransport({command,args,env:{PATH:process.env.PATH},stderr:'pipe'}));
  assert.equal((await client.listTools()).tools.length,3);
  const response = await client.callTool({name:'code_context',arguments:{query:'canAccessProject expired trial'}});
  assert.ok(response.structuredContent.results.some(r=>r.path==='src/auth/permissions.ts'));
  await client.close();
  const answer = JSON.parse(cli('uninstall'));
  assert.equal(answer.status,'uninstalled');
  assert.ok(fs.existsSync(path.join(demo,'.wraith/context.json')));
  assert.ok(!fs.existsSync(installed.command));
});

test('installer refuses conflicts, corrupt packages and traversal without replacing files', t => {
  const folder = temporary(t), source = fakePackage(folder), prefix = path.join(folder,'prefix');
  fs.mkdirSync(path.join(prefix,'bin'),{recursive:true});
  const command = path.join(prefix,'bin',process.platform==='win32'?'wraith-context.cmd':'wraith-context');
  fs.writeFileSync(command,'keep existing command');
  assert.throws(()=>install(prefix,source),/already exists/);
  assert.equal(fs.readFileSync(command,'utf8'),'keep existing command');
  assert.ok(!fs.existsSync(path.join(prefix,'lib/wraith-context')));
  fs.writeFileSync(path.join(source,'launcher.cjs'),'corrupted');
  assert.throws(()=>install(path.join(folder,'clean'),source),/checksum/);
  assert.ok(!fs.existsSync(path.join(folder,'clean')));
  const file = path.join(source,'PREVIEW-MANIFEST.json'), manifest = JSON.parse(fs.readFileSync(file));
  manifest.files={'../../outside.cjs':digest('outside')}; fs.writeFileSync(file,JSON.stringify(manifest));
  assert.throws(()=>install(path.join(folder,'clean'),source),/path/);
});

test('uninstall preserves changed commands, changed payloads, and extra user files', t => {
  const folder = temporary(t), source = fakePackage(folder);
  for (const fault of ['command','payload','extra']) {
    const prefix = path.join(folder,fault), result = install(prefix,source);
    const payload = path.join(prefix,'lib/wraith-context');
    if (fault==='command') {
      fs.unlinkSync(result.command);fs.writeFileSync(result.command,'user replacement');
    } else if (fault==='payload') fs.writeFileSync(path.join(payload,'demo.cjs'),'user modification');
    else fs.writeFileSync(path.join(payload,'notes.txt'),'keep my notes');
    assert.throws(()=>uninstall(prefix),/changed|extra/);
    assert.ok(fs.existsSync(payload));assert.ok(fs.existsSync(result.command));
  }
});

test('installation refuses redirected bin/lib directories', {skip:process.platform==='win32'}, t => {
  const folder = temporary(t), source = fakePackage(folder), prefix=path.join(folder,'prefix'), other=path.join(folder,'other');
  fs.mkdirSync(prefix);fs.mkdirSync(other);fs.symlinkSync(other,path.join(prefix,'lib'));
  assert.throws(()=>install(prefix,source),/symlinks/);
  assert.deepEqual(fs.readdirSync(other),[]);
});
