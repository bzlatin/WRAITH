'use strict';
// Preserve complete bundled-package notices instead of copying vendor source into
// our implementation. Build metadata determines which packages actually shipped.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');

module.exports = function notices(metadata) {
  const packages = new Map();
  for (const input of Object.keys(metadata.inputs)) {
    let directory = path.dirname(path.resolve(input));
    if (!directory.includes(path.sep + 'node_modules' + path.sep)) continue;
    while (directory !== path.dirname(directory)) {
      const manifest = path.join(directory, 'package.json');
      if (fs.existsSync(manifest)) {
        const info = JSON.parse(fs.readFileSync(manifest, 'utf8'));
        if (info.name && info.version) { packages.set(info.name + '@' + info.version, { info, directory }); break; }
      }
      directory = path.dirname(directory);
    }
  }
  const output = ['Third-party software bundled with the local code-context experiment.\n',
    'The Wraith repository license applies to original code; dependencies retain their licenses.\n'];
  for (const [name, { info, directory }] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
    const licenseFiles = fs.readdirSync(directory).filter(file => /^(?:licen[cs]e|copyright|notice)(?:\.|$)/i.test(file));
    output.push(`\n${'='.repeat(72)}\n${name}\nDeclared license: ${info.license || 'see package'}\n`);
    if (!licenseFiles.length) throw new Error('Missing bundled dependency notice: ' + name);
    for (const file of licenseFiles) {
      if (fs.statSync(path.join(directory, file)).isFile()) output.push(fs.readFileSync(path.join(directory, file), 'utf8') + '\n');
    }
  }
  const text = output.join('\n');
  fs.writeFileSync(path.join(root, 'THIRD_PARTY_NOTICES.txt'), text);
  fs.writeFileSync(path.join(root, 'dist/THIRD_PARTY_NOTICES.txt'), text);
  fs.copyFileSync(path.join(root, '../../LICENSE'), path.join(root, 'dist/LICENSE'));
  return packages.size;
};
