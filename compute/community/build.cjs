#!/usr/bin/env node
/* Source-driven, offline build of the board, portable reports, feed and source kit. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=__dirname,COMPUTE=path.resolve(ROOT,'..'),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const read=p=>fs.readFileSync(p),json=o=>JSON.stringify(o,null,2)+'\n';
function write(p,b){fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,b);}
// The report/record engines are generated projections owned by the instrument.
for(const n of ['workload-engine.cjs','qualified-engine.cjs']){const src=path.join(COMPUTE,'adapters',n);if(fs.existsSync(src))write(path.join(ROOT,n),read(src));}
const C=require('./core.cjs'),U=require('./cli.cjs');
function crc32(b){let c=0xffffffff;for(const x of b){c^=x;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
function zipStored(entries){let offset=0,parts=[],directory=[];for(const [name,bytes] of entries){const n=Buffer.from(name),b=Buffer.isBuffer(bytes)?bytes:Buffer.from(bytes),crc=crc32(b),local=Buffer.alloc(30),central=Buffer.alloc(46);local.writeUInt32LE(0x04034b50);local.writeUInt16LE(20,4);local.writeUInt16LE(0x800,6);local.writeUInt16LE(0x5b38,12);local.writeUInt32LE(crc,14);local.writeUInt32LE(b.length,18);local.writeUInt32LE(b.length,22);local.writeUInt16LE(n.length,26);central.writeUInt32LE(0x02014b50);central.writeUInt16LE(0x314,4);central.writeUInt16LE(20,6);central.writeUInt16LE(0x800,8);central.writeUInt16LE(0x5b38,14);central.writeUInt32LE(crc,16);central.writeUInt32LE(b.length,20);central.writeUInt32LE(b.length,24);central.writeUInt16LE(n.length,28);central.writeUInt32LE((0o100644<<16)>>>0,38);central.writeUInt32LE(offset,42);parts.push(local,n,b);directory.push(central,n);offset+=local.length+n.length+b.length;}
 const cd=Buffer.concat(directory),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(cd.length,12);end.writeUInt32LE(offset,16);return Buffer.concat([...parts,cd,end]);}
function build(){const config=JSON.parse(read(path.join(ROOT,'data/release.json'))),records=config.records.map(id=>{if(!/^[a-f0-9]{64}$/.test(id))throw Error('Invalid release record');const p=C.verify(JSON.parse(read(path.join(ROOT,'data/records',id+'.json'))));if(p.sha256!==id)throw Error('Content-addressed filename mismatch');if(C.privacy(p).length)throw Error('Public privacy hold');return p;});if(new Set(config.records).size!==config.records.length)throw Error('Duplicate release record');
 const links={prices:'index.html',rating:'../clustermax-challenge/',instrument:'../hot-aisle/',kit:'community-kit.zip',docs:'community/README.md'},rendered=U.renderPage(config,records,{record_base:'community/data/records/',report_base:'community/r/',built_at:config.built_at,links});
 write(path.join(COMPUTE,'results.html'),rendered.html);write(path.join(ROOT,'board.json'),json(rendered.board));write(path.join(ROOT,'feed.json'),json(U.feed({...config,origin:'Second Run public source-bound seed'},records,[],config.built_at)));
 for(const p of records)write(path.join(ROOT,'r',p.sha256+'.html'),U.renderResult(p));
 const allowed=['core.cjs','workload-engine.cjs','qualified-engine.cjs','app.js','style.css','template.html','cli.cjs','build.cjs','import-seed.cjs','README.md','board.json','feed.json','data/release.json','data/source-manifest.json','tests/test_core.cjs','tests/browser.py','tests/browser.cjs','LICENSE','QUALIFICATION.json'];
 const files=[['compute/results.html',read(path.join(COMPUTE,'results.html'))]];
 for(const n of allowed){const p=path.join(ROOT,n);if(!fs.existsSync(p))throw Error('Required source missing '+n);files.push(['compute/community/'+n,read(p)]);}
 // Include the existing static decision desk; no service, credential or generated workload is bundled.
 for(const n of ['index.html','LICENSE'])if(fs.existsSync(path.join(COMPUTE,n)))files.push(['compute/'+n,read(path.join(COMPUTE,n))]);
 for(const id of config.records){for(const n of ['data/records/'+id+'.json','r/'+id+'.html'])files.push(['compute/community/'+n,read(path.join(ROOT,n))]);}
 files.sort((a,b)=>a[0].localeCompare(b[0]));const manifest={schema:'second-run/community-release@1',version:config.version,scope:config.release_scope,files:files.map(([p,b])=>({path:p,bytes:b.length,sha256:sha(b)}))};write(path.join(ROOT,'MANIFEST.json'),json(manifest));files.push(['compute/community/MANIFEST.json',Buffer.from(json(manifest))]);write(path.join(COMPUTE,'community-kit.zip'),zipStored(files));return {records:records.length,files:files.length,page_sha256:sha(read(path.join(COMPUTE,'results.html'))),kit_sha256:sha(read(path.join(COMPUTE,'community-kit.zip')))};}
module.exports={build,zipStored};if(require.main===module)console.log(JSON.stringify(build(),null,2));
