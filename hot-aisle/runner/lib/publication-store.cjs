'use strict';
const fs=require('node:fs'),path=require('node:path');
const contract=require('./publication.cjs'),record=require('./record.cjs');
const VALID=/^rec-[A-Za-z0-9._-]+-[a-f0-9]{16}$/;
function read(store,id) {
  if(!VALID.test(id))throw Error('Invalid publication identifier.');
  const root=path.resolve(store.root,'published'),dir=path.join(root,id),file=path.join(dir,'bundle.json');
  if(fs.lstatSync(dir).isSymbolicLink()||fs.lstatSync(file).isSymbolicLink())throw Error('Symbolic publication refused.');
  if(!fs.realpathSync(file).startsWith(fs.realpathSync(root)+path.sep)||fs.statSync(file).size>32*1024*1024)throw Error('Publication outside read boundary.');
  const b=contract.verify(JSON.parse(fs.readFileSync(file,'utf8')));
  if(contract.projection(b).publication_id!==id)throw Error('Publication ID does not match record identity.');
  return b;
}
function list(store) {
  const publications=[],holds=[];
  for(const entry of fs.readdirSync(path.join(store.root,'published'),{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    if(!VALID.test(entry.name))continue;
    if(publications.length+holds.length>=100){holds.push({reason:'Publication listing limit reached.'});break;}
    try{const b=read(store,entry.name),{cell,...p}=contract.projection(b);publications.push(p);}catch{holds.push({id:entry.name,reason:'Publication failed verification.'});}
  }
  return {schema:'hot-aisle/publications@1',publications,holds};
}
function publish(store,rec) {
  const b=contract.bundle(rec),id=contract.projection(b).publication_id;
  const parent=path.join(store.root,'published'),dir=path.join(parent,id);
  if(fs.existsSync(dir)){
    if(contract.identity(read(store,id))!==contract.identity(b))throw Error('Existing publication differs.');
    return result();
  }
  const temp=fs.mkdtempSync(path.join(parent,'.pending-'));
  const json=x=>JSON.stringify(x,null,2)+'\n';
  const files={'record.json':json(rec),'evidence.json':json(b.evidence),'bundle.json':json(b),
    'headline.json':json(record.headline(rec,{published_on:new Date().toISOString().slice(0,10),evidence_url:'evidence.json',report_url:'report.html'})),
    'report.html':record.receipt(rec),'summary.txt':record.summary(rec)+'\n'};
  try{for(const [name,content] of Object.entries(files))fs.writeFileSync(path.join(temp,name),content,{flag:'wx'});fs.renameSync(temp,dir);}catch(e){fs.rmSync(temp,{recursive:true,force:true});throw e;}
  return result();
  function result(){return {published:dir,publication_id:id,record_id:rec.id,record_sha256:rec.sha256,
    files:['bundle.json','record.json','evidence.json','headline.json','report.html','summary.txt'],synthetic:rec.synthetic,
    note:'Immutable local publication. Available to a configured decision desk; no network publication performed.'};}
}
module.exports={read,list,publish};
