/* Read-only publication client. The configured runner owns every execution. */
'use strict';
const crypto=require('node:crypto');
const Q=require('./qualified-engine.cjs');
function configure(value){
 if(!value)return null;
 const u=new URL(value);
 if(u.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(u.hostname)||u.username||u.password||u.search||u.hash||!['','/'].includes(u.pathname))throw Error('Runner must be an explicit HTTP loopback origin, without credentials, paths, queries or fragments.');
 return u.origin;
}
function create(value,catalogBytes){
 const origin=configure(value),catalogHash=crypto.createHash('sha256').update(catalogBytes).digest('hex');
 async function get(route){
  if(!origin)throw Error('No instrument configured.');
  const response=await fetch(origin+route,{redirect:'error',headers:{Accept:'application/json'},signal:AbortSignal.timeout(5000)});
  if(!response.ok)throw Error('Instrument returned '+response.status+'.');
  const chunks=[];let size=0;const reader=response.body.getReader();
  try{for(;;){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>32*1024*1024)throw Error('Instrument response exceeds 32 MiB.');chunks.push(value);}}finally{await reader.cancel().catch(()=>{});}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
 }
 async function list(){
  if(!origin)return {schema:'second-run/instrument-publications@1',status:'NOT_CONFIGURED',publications:[],holds:[]};
  const [result,source]=await Promise.all([get('/api/publications'),get('/api/catalog')]);
  if(!Array.isArray(result.publications)||!Array.isArray(result.holds))throw Error('Unsupported instrument publication listing.');
  if(result.publications.length>100)throw Error('Instrument publication listing exceeds the limit.');
  return {schema:'second-run/instrument-publications@1',status:'CONNECTED',observedAt:new Date().toISOString(),origin,
   catalog:{state:source.sha256===catalogHash?'MATCH':'DIFFERENT_SNAPSHOT',desk_sha256:catalogHash,instrument_sha256:source.sha256,instrument_reviewed_on:source.catalog?.reviewedOn},
   publications:result.publications,holds:result.holds};
 }
 async function read(id){
  if(typeof id!=='string'||!/^rec-[A-Za-z0-9._-]+-[a-f0-9]{16}$/.test(id))throw Error('Use a published record ID.');
  const bundle=await get('/api/publications/'+encodeURIComponent(id));
  Q.publication.verify(bundle);
  if(Q.publication.projection(bundle).publication_id!==id)throw Error('Publication ID differs from its record.');
  return bundle;
 }
 return {origin,list,read};
}
module.exports={configure,create};
