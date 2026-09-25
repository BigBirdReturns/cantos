'use strict';
// Differential harness: runs the engine embedded in index.html over a forge document from stdin
// and returns per-chunk SHA-256 digests of canonical output (or raw items when verbose).
// Canonical form matches scripts/forge.py canon(): sorted keys, no spaces, integral floats as ints.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const html=fs.readFileSync(path.join(__dirname,'..','index.html'),'utf8');
const m=html.match(/<script id="shelf-engine">([\s\S]*?)<\/script>/);
if(!m){console.error('shelf-engine missing');process.exit(2);}
vm.runInThisContext(m[1],{filename:'index.html#shelf-engine'});const S=globalThis.Shelf;
function canon(v){
 if(v===undefined)return 'null';
 if(v===null||typeof v!=='object')return JSON.stringify(v);
 if(Array.isArray(v))return '['+v.map(canon).join(',')+']';
 return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k]===undefined?null:v[k])).join(',')+'}';
}
const digest=items=>{const h=crypto.createHash('sha256');for(const s of items){h.update(s,'utf8');h.update('\n');}return h.digest('hex');};
const doc=JSON.parse(fs.readFileSync(0,'utf8'));
const cards=doc.cards,chunk=doc.chunk||2000;
const sections={
 validate:()=>cards.map(c=>canon(S.validateCard(c))),
 which:()=>doc.queries.map(q=>canon(S.which(cards.slice(0,doc.which_n),q.unit,q.period,q.measured))),
 compose:()=>doc.pairs.map(([a,b,p])=>canon(S.compose(cards[a],cards[b],p))),
};
if(doc.verbose&&doc.only){
 const items=sections[doc.only.section]();
 process.stdout.write(JSON.stringify({items:items.slice(doc.only.chunk*chunk,(doc.only.chunk+1)*chunk)}));
}else{
 const out={};
 for(const [k,fn] of Object.entries(sections)){const items=fn();const d=[];for(let i=0;i<items.length;i+=chunk)d.push(digest(items.slice(i,i+chunk)));out[k]=d;}
 process.stdout.write(JSON.stringify({digests:out}));
}
