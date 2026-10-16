'use strict';
const path = require('node:path');
const fs = require('node:fs');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const result = esbuild.buildSync({ entryPoints: [path.join(root, 'cli.cjs')], outfile: path.join(root, 'dist/wraith-context.cjs'),
  bundle: true, platform: 'node', target: 'node22', format: 'cjs', legalComments: 'eof', metafile: true });
const dependencies = require('./notices.cjs')(result.metafile);
fs.writeFileSync(path.join(root, 'dist/build-meta.json'), JSON.stringify(result.metafile, null, 2) + '\n');
fs.chmodSync(path.join(root, 'dist/wraith-context.cjs'), 0o755);
for (const name of ['launcher.cjs','installer.cjs','demo.cjs']) {
  fs.copyFileSync(path.join(root,'preview',name), path.join(root,'dist',name));
}
fs.chmodSync(path.join(root,'dist/launcher.cjs'),0o755);
// Only this allowlist ships. Build metadata and local study artifacts stay out.
const payload = ['wraith-context.cjs','launcher.cjs','installer.cjs','demo.cjs','LICENSE','THIRD_PARTY_NOTICES.txt'];
function copyDemo(folder, prefix = '') {
  for (const entry of fs.readdirSync(folder,{withFileTypes:true})) {
    const relative = prefix+entry.name, source = path.join(folder,entry.name);
    if (entry.isDirectory()) copyDemo(source,relative+'/');
    else if (entry.isFile()) {
      const name = 'demo/'+relative;
      fs.mkdirSync(path.dirname(path.join(root,'dist',name)),{recursive:true});
      fs.copyFileSync(source,path.join(root,'dist',name)); payload.push(name);
    } else throw new Error('Unexpected non-file in demo.');
  }
}
copyDemo(path.join(root,'demo'));
const crypto = require('node:crypto');
const files = Object.fromEntries(payload.sort().map(name => [name,
  crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'dist',name))).digest('hex')]));
fs.writeFileSync(path.join(root,'dist/PREVIEW-MANIFEST.json'),JSON.stringify({schema_version:1,
  product:'wraith-context',version:'0.1.0-preview.1',files},null,2)+'\n');
console.log(`Built dist/wraith-context.cjs with ${dependencies} dependency notices; requires Node.js 22.12+. No runtime npm install needed.`);
