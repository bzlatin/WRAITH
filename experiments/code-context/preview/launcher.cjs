#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
function codexConfig(argv) {
  const allowReads = argv.filter(arg => arg === '--allow-read-tools').length;
  const options = argv.filter(arg => arg !== '--allow-read-tools');
  if (allowReads > 1 || options.length !== 2 || options[0] !== '--root') throw new Error('Usage: wraith-context codex-config --root /path/to/checkout [--allow-read-tools]');
  const root = fs.realpathSync(options[1]);
  const actual = execFileSync('git', ['-c','core.fsmonitor=false','-c','core.hooksPath=','-C',root,'rev-parse','--show-toplevel'],
    { encoding:'utf8', stdio:['ignore','pipe','pipe'], timeout:15000 }).trim();
  if (fs.realpathSync(actual) !== root) throw new Error('Select the checkout root.');
  // JSON basic strings are TOML-compatible for ordinary paths. Escape controls
  // explicitly; generated text is data, never a shell command.
  const toml = s => JSON.stringify(s);
  let result = '[mcp_servers.wraith_context]\ncommand = '+toml(process.execPath)+'\nargs = '+JSON.stringify([
    path.join(__dirname,'wraith-context.cjs'),'mcp','--root',root])+'\n';
  if (allowReads) {
    result += '# Allow these three local read tools without a per-call prompt.\n';
    for (const tool of ['code_context','code_symbols','code_references']) {
      result += '\n[mcp_servers.wraith_context.tools.'+tool+']\napproval_mode = "auto"\n';
    }
  }
  return result;
}
const [command, ...args] = process.argv.slice(2);
try {
  const [major,minor] = process.versions.node.split('.').map(Number);
  if (major < 22 || (major === 22 && minor < 12)) throw new Error('Node.js 22.12+ is required.');
  if (command === 'codex-config') process.stdout.write(codexConfig(args));
  else if (command === 'demo') require('./demo.cjs').main(args);
  else if (command === 'uninstall') require('./installer.cjs').main(['uninstall',...args]);
  else if (command === '--preview-version') console.log('0.1.0-preview.1');
  else {
    if (!command || ['--help','-h','help'].includes(command)) {
      console.log('Preview helpers: demo --directory PATH | codex-config --root PATH [--allow-read-tools] | uninstall\nCore commands:');
    }
    require('./wraith-context.cjs');
  }
} catch (e) { console.error(e.message); process.exitCode = 2; }
