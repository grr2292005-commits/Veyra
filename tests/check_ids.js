const fs = require('fs');
const html = fs.readFileSync('plugin/index.html', 'utf8');
const js = fs.readFileSync('plugin/index.js', 'utf8');
const elBlock = js.match(/const el = \{([\s\S]*?)\n  \};/)[1];
const idMatches = [...elBlock.matchAll(/document\.getElementById\(['"]([^'"]+)['"]\)/g)].map(m => m[1]);
console.log('Total IDs in el:', idMatches.length);
const missing = [];
for (const id of idMatches) {
  const pattern1 = `id="${id}"`;
  const pattern2 = `id='${id}'`;
  if (!html.includes(pattern1) && !html.includes(pattern2)) {
    missing.push(id);
  }
}
console.log('Missing IDs:', missing);
