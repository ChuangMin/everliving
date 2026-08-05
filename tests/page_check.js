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
  '  globalThis.__bench = bench; globalThis.__setBench = setBench;' +
  '  globalThis.__setAuto = setAuto; globalThis.__turn = turn; })();');

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
global.location = { search: '' };             // the ?scene= hook reads this on boot
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

// The water has to run continuously, and continuity is a property of the geometry
// the CSS then slides: the path must extend a full wave period past both edges, or
// the loop shows a bare gap when it reaches the end of its travel.
const PERIOD = 2 * Math.PI * 68;
const waveX = nodes.get('wave').getAttribute('d')
  .split(/[ML]/).slice(1).map(s => parseFloat(s.trim().split(' ')[0]));
check(Math.min(...waveX) <= 0 && Math.max(...waveX) >= 1000 + PERIOD,
      `wave spans ${Math.min(...waveX)}..${Math.max(...waveX)}, covering a ${PERIOD.toFixed(0)}-unit slide`);

// The glints on the water were the one thing still reshuffling on every redraw,
// which read as a stutter rather than as water.
globalThis.__draw('潮線'); const s1 = nodes.get('shimmer').children.map(n => n.getAttribute('x'));
globalThis.__draw('潮線'); const s2 = nodes.get('shimmer').children.map(n => n.getAttribute('x'));
check(s1.length > 0 && s1.join() === s2.join(),
      `water glints are stable across redraws (${s1.length} of them)`);

// The camera leans toward whatever is happening. Without this the drift is decoration;
// with it, it's the thing that can carry the player's eye to an event.
globalThis.__draw('工作間', '停電');
const aimed = nodes.get('camera').style.transformOrigin;
globalThis.__draw('工作間', null);
const idle = nodes.get('camera').style.transformOrigin;
check(aimed === '820px 120px' && idle === '500px 210px',
      `camera aims at the action (${aimed}) and returns to centre (${idle})`);

try {
  globalThis.__apply({
    state: {'手部狀態':'擦傷', '持有物':'半組幫浦零件'},
    threads: ['等你回覆要不要幫他找零件'],
    ledger: {nights:3, events:7, exchanges:12, resolved:1},
    scene: '潮線',
    delegations: ['去回收場東邊找一個還能用的壓力閥'],
    assets: [{kind:'video', ref:'clips/a.webm'}],
  });
  globalThis.__setBench(true);
  check(nodes.get('tally').children.length === 4
        && nodes.get('benchState').children.length === 2
        && nodes.get('benchThreads').children.length === 1
        && nodes.get('benchPlace').textContent === '潮線'
        && nodes.get('bench').getAttribute('data-open') === '1',
        'workbench fills in and opens');

  // The other direction from threads: what you're waiting on him for. It's only ever
  // settled while you're away, so between asking and finding out this is the one place
  // a delegation is visible at all.
  check(nodes.get('benchAsks').children.length === 1
        && nodes.get('benchAsksEmpty').hidden === true,
        'what you asked him to do shows up on the bench');

  globalThis.__apply({state:{}, threads:[], delegations:[],
                      ledger:{nights:0,events:0,exchanges:0,resolved:0}});
  globalThis.__bench();
  check(nodes.get('benchState').children.length === 0
        && nodes.get('benchThreads').children.length === 0
        && nodes.get('benchAsks').children.length === 0,
        'workbench empties instead of showing stale rows');
} catch (e) { check(false, `workbench threw: ${e.message}`); }

// What's happening, on top of where he is. Each one has to actually draw something,
// or the tag is costing prompt room and buying nothing.
for(const action of ['焊接','停電','淹水','起霧']){
  try {
    globalThis.__draw('工作間', action);
    const n = nodes.get('action').children.length;
    check(n > 0, `${action} draws ${n} elements over the scene`);
  } catch (e) { check(false, `${action} threw: ${e.message}`); }
}
try {
  globalThis.__draw('工作間', null);
  check(nodes.get('action').children.length === 0,
        'clearing the action empties the overlay rather than leaving it stuck');
} catch (e) { check(false, `clearing action threw: ${e.message}`); }

// Handing the seat to an agent, and taking it back. The loop itself can't run here
// (fetch never resolves), which is the point: toggling must be safe on its own.
try {
  globalThis.__setAuto(true);
  const onLabel = nodes.get('autoBtn').textContent;
  const inputLocked = nodes.get('msg').hidden === undefined ? true : true;
  globalThis.__setAuto(false);
  const offLabel = nodes.get('autoBtn').textContent;
  check(onLabel === '停止代打' && offLabel === '讓 AI 代打',
        `autoplay switch toggles its label (${onLabel} / ${offLabel})`);

  globalThis.__turn('訪客(AI)', '最近潮位怎麼樣?', true, [{kind:'video', ref:'clips/a.webm'}]);
  const last = nodes.get('log').children.slice(-1)[0];
  check(last && last.children.length === 3, 'an agent turn renders with its assets beside it');
} catch (e) { check(false, `autoplay switch threw: ${e.message}`); }

// A payload carrying an error must not also try to redraw with missing fields.
try {
  globalThis.__apply({error: '模型拒絕回應這個請求。'});
  check(true, 'an error payload is handled without throwing');
} catch (e) { check(false, `error payload threw: ${e.message}`); }

console.log(bad ? `\n${bad} FAILURES` : '\nall page checks passed');
process.exit(bad ? 1 : 0);
