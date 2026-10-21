import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { buildSync } = require('esbuild');
function load() {
 const result = buildSync({entryPoints:['src/navigation.ts'],bundle:true,write:false,platform:'node',format:'cjs'});
 const module = {exports:{}}; new Function('require','module','exports',result.outputFiles[0].text)(require,module,module.exports); return module.exports;
}
test('bookmark routes round-trip every destination and encoded entity IDs, retaining old aliases', () => {
 const {parseRoute,routeHref,SECTIONS} = load();
 assert.equal(SECTIONS.length,10);
 for (const {id} of SECTIONS) assert.deepEqual(parseRoute(routeHref({section:id,id:'a/b #?'})),{section:id,id:'a/b #?'});
 assert.deepEqual(parseRoute('#inbox'),{section:'inbox'});
 assert.deepEqual(parseRoute('#thoughts'),{section:'inbox'});
 assert.deepEqual(parseRoute('#workspace'),{section:'status'});
 assert.deepEqual(parseRoute('#research-start'),{section:'research'});
 assert.deepEqual(parseRoute('#/%zz'),{section:'inbox'});
});
