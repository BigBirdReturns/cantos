'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {sourceLines}=require('../batch_owner.cjs');
function removeFixture(dir){
 const target=fs.realpathSync(dir),root=fs.realpathSync(os.tmpdir());
 assert.equal(path.dirname(target),root);
 assert.ok(path.basename(target).startsWith('cantos-packet-'));
 fs.rmSync(target,{recursive:true,force:true});
}

test('native packet processing exerts backpressure on source input',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cantos-packet-stream-'));
 const file=path.join(dir,'rows.jsonl');
 const block=Buffer.from(JSON.stringify({fixture:true,text:'x'.repeat(1020)})+'\n');
 const fd=fs.openSync(file,'wx');
 try{for(let i=0;i<20000;i++)fs.writeSync(fd,block);}finally{fs.closeSync(fd);}
 let consumed=0;
 const hash={update(chunk){consumed+=chunk.length;}};
 const lines=sourceLines(file,hash);
 try{
  await lines.next();
  await new Promise(resolve=>setTimeout(resolve,50));
  assert.ok(consumed<1024*1024,`paused packet producer consumed ${consumed} bytes`);
 }finally{
  await lines.return();
  removeFixture(dir);
 }
});

test('stream keeps raw identity and Unicode across chunk and line boundaries',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cantos-packet-unicode-'));
 const file=path.join(dir,'rows.jsonl');
 const expected=[' '.repeat(65534)+'\u2122','{"text":"\u2014"}','last line'];
 const raw=Buffer.from(expected.join('\r\n'));
 fs.writeFileSync(file,raw,{flag:'wx'});
 const hash=crypto.createHash('sha256'),actual=[];
 try{
  for await(const line of sourceLines(file,hash))actual.push(line);
  assert.deepEqual(actual,expected);
  assert.equal(hash.digest('hex'),crypto.createHash('sha256').update(raw).digest('hex'));
 }finally{removeFixture(dir);}
});
