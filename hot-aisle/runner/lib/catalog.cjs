'use strict';
/* data/catalog.json is a generated exact snapshot of compute/data/catalog.json.
   Live tenant quotes remain separate supplied observations and never renew its date. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const FILE=path.resolve(__dirname,'../../data/catalog.json');
function snapshot(){const bytes=fs.readFileSync(FILE),catalog=JSON.parse(bytes);if(catalog.schema!=='second-run/compute-catalog@1'||!Array.isArray(catalog.offers))throw Error('Unsupported catalogue.');return {schema:'hot-aisle/catalogue-reference@1',sha256:crypto.createHash('sha256').update(bytes).digest('hex'),catalog};}
function quote(id,asOf=snapshot().catalog.reviewedOn){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(asOf))throw Error('Use an ISO quote date.');
  const {catalog,sha256}=snapshot(),offer=catalog.offers.find(o=>o.id===id);if(!offer)throw Error('Unknown catalogue offer.');
  let rate=offer.rate;for(const schedule of [...(offer.schedules||[])].sort((a,b)=>a.effectiveOn.localeCompare(b.effectiveOn)))if(schedule.effectiveOn<=asOf)rate=schedule.rate;
  const provider=catalog.providers.find(p=>p.id===offer.provider),source=catalog.sources[offer.source];
  return {provider:provider.name+' '+offer.gpu,gpus:offer.gpus,rate,extra:0,source:source.url,
    period:asOf+' scenario; reviewed '+catalog.reviewedOn,quote:offer.terms,
    catalog_ref:{sha256,offer_id:id,reviewed_on:catalog.reviewedOn,as_of:asOf},minimum_hours:offer.minimumHours};
}
module.exports={snapshot,quote};
