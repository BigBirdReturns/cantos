'use strict';
// Test authoring through the unchanged native Research Desk owner.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const app=fs.readFileSync(path.resolve(__dirname,'../../research-desk/app.html'),'utf8');
const scripts=[...app.matchAll(/<script id="research-core">([\s\S]*?)<\/script>/g)];
if(scripts.length!==1)throw Error('Native core is absent');
vm.runInThisContext(scripts[0][1]);const C=globalThis.ResearchCore;
let text='';process.stdin.setEncoding('utf8');
process.stdin.on('data',c=>text+=c);
process.stdin.on('end',async()=>{try{
 const input=JSON.parse(text);
 const ws=input.packet?await C.verifyPacket(input.packet):C.empty('Retained procedure qualification');
 for(const record of input.records)await C.put(ws,record,'Explicit native test author','2026-09-28T18:00:00Z');
 const packet=await C.pack(ws);await C.verifyPacket(packet);
 process.stdout.write(JSON.stringify(packet)+'\n');
}catch(e){console.error(e);process.exitCode=1;}});
