/* Runs the page's JavaScript against a stub DOM.
 *
 * The Python tests can prove the server sends the right JSON, but they cannot see a
 * typo in the browser code — the page would serve 200 and then render nothing. That
 * failure mode has already cost this project a playtest once, so the drawing code is
 * actually executed here: every scene rendered, the workbench opened and emptied.
 *
 * Deliberately not a real DOM implementation. A stub keeps this dependency-free and
 * fails loudly on the things that matter (a missing element, a NaN coordinate, an
 * exception) rather than quietly absorbing them the way a browser sometimes does.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'everliving', 'static', 'index.html'), 'utf8');

let js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
js = js.replace(/\}\)\(\);\s*$/,
  '; globalThis.__draw = drawScene; globalThis.__apply = apply;' +
  '  globalThis.__bench = bench; globalThis.__setBench = setBench; })();');

let created = 0;
const nodes = new Map();
function makeNode(name){
  return {
    name, children: [], attrs: {},
    setAttribute(k, v){
      if(v === undefined || v === null || (typeof v === 'number' && Number.isNaN(v)))
        throw new Error(`${name}.${k} set to ${v}`);
      if(String(v).includes('NaN')) throw new Error(`${name}.${k} contains NaN: ${v}`);
      this.attrs[k] = String(v);
    },
    getAttribute(k){ return this.attrs[k]; },
    removeAttribute(k){ delete this.attrs[k]; },
    appendChild(c){ this.children.push(c); return c; },
    cloneNode(){ const n = makeNode(this.name); n.children = [...this.children]; return n; },
    scrollIntoView(){}, addEventListener(){}, focus(){},
    set textContent(v){ this._t = v; this.children = []; },
    get textContent(){ return this._t; },
    set hidden(v){ this._h = v; }, get hidden(){ return this._h; },
    get firstElementChild(){ return this.children[0] || makeNode('empty'); },
    style: {}, classList: { add(){}, remove(){} },
  };
}
global.document = {
  getElementById(id){ if(!nodes.has(id)) nodes.set(id, makeNode(id)); return nodes.get(id); },
  createElementNS(ns, tag){ created++; return makeNode(tag); },
  createElement(tag){ created++; return makeNode(tag); },
  createTextNode(){ return makeNode('#text'); },
  title: '',
};
global.fetch = () => new Promise(() => {});   // boot path stays pending, never resolves
global.setInterval = () => 0;
global.addEventListener = () => {};
global.navigator = { sendBeacon(){} };
global.Blob = function(){};

eval(js);

let bad = 0;
const check = (ok, msg) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${msg}`); if(!ok) bad++; };

for(const scene of ['工作間','配電所','港城','潮線','回收場','機器廠']){
  created = 0;
  try {
    globalThis.__draw(scene);
    const y = parseFloat(nodes.get('waterRect').getAttribute('y'));
    check(created > 40 && nodes.get('place').textContent === scene && y > 200 && y < 300,
          `${scene} drew ${created} elements, waterY=${y.toFixed(1)}`);
  } catch (e) { check(false, `${scene} threw: ${e.message}`); }
}

// A place must look the same each time you come back to it.
globalThis.__draw('港城'); const a = nodes.get('mid').children.length;
globalThis.__draw('港城'); const b = nodes.get('mid').children.length;
check(a === b, `scene is stable across redraws (${a} vs ${b})`);

try {
  globalThis.__apply({
    state: {'手部狀態':'擦傷', '持有物':'半組幫浦零件'},
    threads: ['等你回覆要不要幫他找零件'],
    ledger: {nights:3, events:7, exchanges:12, resolved:1},
    scene: '潮線',
    assets: [{kind:'video', ref:'clips/a.webm'}],
  });
  globalThis.__setBench(true);
  check(nodes.get('tally').children.length === 4
        && nodes.get('benchState').children.length === 2
        && nodes.get('benchThreads').children.length === 1
        && nodes.get('benchPlace').textContent === '潮線'
        && nodes.get('bench').getAttribute('data-open') === '1',
        'workbench fills in and opens');

  globalThis.__apply({state:{}, threads:[], ledger:{nights:0,events:0,exchanges:0,resolved:0}});
  globalThis.__bench();
  check(nodes.get('benchState').children.length === 0
        && nodes.get('benchThreads').children.length === 0,
        'workbench empties instead of showing stale rows');
} catch (e) { check(false, `workbench threw: ${e.message}`); }

// A payload carrying an error must not also try to redraw with missing fields.
try {
  globalThis.__apply({error: '模型拒絕回應這個請求。'});
  check(true, 'an error payload is handled without throwing');
} catch (e) { check(false, `error payload threw: ${e.message}`); }

console.log(bad ? `\n${bad} FAILURES` : '\nall page checks passed');
process.exit(bad ? 1 : 0);
