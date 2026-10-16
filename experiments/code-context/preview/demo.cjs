'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const QUERY = 'Find canAccessProject, its API caller and tests for an expired trial';
function main(argv) {
  if (argv.length !== 2 || argv[0] !== '--directory' || !argv[1]) throw new Error('Usage: wraith-context demo --directory NEW_DIRECTORY');
  const folder = path.resolve(argv[1]);
  fs.mkdirSync(folder); // Never modify an existing directory or Git checkout.
  const copy = source => {
    for (const entry of fs.readdirSync(source, { withFileTypes:true })) {
      const relative = path.relative(path.join(__dirname,'demo'),path.join(source,entry.name));
      const target = path.join(folder,relative);
      if (entry.isDirectory()) { fs.mkdirSync(target); copy(path.join(source,entry.name)); }
      else if (entry.isFile()) fs.copyFileSync(path.join(source,entry.name),target,fs.constants.COPYFILE_EXCL);
      else throw new Error('Unexpected demo file.');
    }
  };
  copy(path.join(__dirname,'demo'));
  const env = {};
  for (const key of ['PATH','SYSTEMROOT','TEMP','TMP','TMPDIR','LANG']) if (process.env[key]) env[key] = process.env[key];
  const git = (...args) => execFileSync('git', ['-c','core.hooksPath=','-c','core.fsmonitor=false',
    '-c','user.name=Demo','-c','user.email=demo@example.invalid','-C',folder,...args], { env, stdio:'pipe',timeout:15000 });
  git('init','-b','main'); git('add','.'); git('commit','-m','Local code-context demonstration');
  const raw = execFileSync(process.execPath, [path.join(__dirname,'wraith-context.cjs'),'context',QUERY,
    '--root',folder,'--cache',path.join(folder,'.wraith/cache')], { env,encoding:'utf8',maxBuffer:2*1024*1024,timeout:30000 });
  const context = JSON.parse(raw);
  fs.mkdirSync(path.join(folder,'.wraith'),{ recursive:true });
  fs.writeFileSync(path.join(folder,'.wraith/context.json'),raw,{ flag:'wx',mode:0o600 });
  execFileSync(process.execPath, ['--experimental-strip-types','--test','tests/access.test.mjs'],
    { cwd:folder,env,encoding:'utf8',timeout:30000,stdio:['ignore','pipe','pipe'] });
  console.log(JSON.stringify({status:'ready',directory:folder,query:QUERY,
    cited_files:[...new Set(context.results.map(r=>r.path))],context:path.join(folder,'.wraith/context.json'),
    tests_passed:true,scope:'Prepared demonstration, no model calls or product-value evidence'},null,2));
}
module.exports = { main, QUERY };
