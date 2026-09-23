/* Native browser navigation over the actual instrument, SSE and read-only desk. */
'use strict';
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.resolve(process.env.SEAM_QA_DIR||'seam-browser-qa');
const {Store}=require('../../hot-aisle/runner/lib/store.cjs'),{Jobs}=require('../../hot-aisle/runner/lib/jobs.cjs');
const local=require('../../hot-aisle/runner/lib/adapters/local.cjs'),instrument=require('../../hot-aisle/runner/lib/server.cjs');
const desk=require('../../compute/scripts/connect.cjs'),Q=require('../../compute/adapters/qualified-engine.cjs');
const checks=[],errors=[],external=[],requests=[];
function check(name,value){assert.ok(value,name);checks.push(name);}
function listen(page){page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{requests.push(r.url());const u=new URL(r.url());if(!['127.0.0.1','localhost'].includes(u.hostname)&&u.protocol!=='blob:')external.push(r.url());});}
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});const home=fs.mkdtempSync(path.join(os.tmpdir(),'compute-seam-browser-')),store=new Store(home),jobs=new Jobs(store);
 const fake=await local.startFakeApi(),runner=instrument.createServer({store,jobs,fakeApi:fake}),origin=await runner.listenOn();
 const service=await desk.startHttp(desk.makeWorkspace({runner:origin}));let browser;
 try{
  browser=await chromium.launch();const ctx=await browser.newContext({viewport:{width:1440,height:960},acceptDownloads:true,colorScheme:'light'});
  const operator=await ctx.newPage();listen(operator);await operator.goto(origin,{waitUntil:'networkidle'});
  await operator.waitForFunction(()=>document.querySelector('#rail-state')?.textContent.includes('connected'));
  check('runner native environment observed',/MI300X/.test(await operator.locator('#rail-env').innerText()));
  await operator.click('#open-plan');await operator.fill('#f-concurrency','1, 8');await operator.fill('#f-repeats','1');await operator.fill('#f-num_prompts','24');
  await operator.click('#preview');await operator.waitForSelector('#approve-start');const hash=(await operator.locator('#instrument .kv .v.mono').innerText()).trim();check('approval presents exact plan identity',/^[a-f0-9]{64}$/.test(hash));
  await operator.click('#approve-start');await operator.waitForFunction(()=>/from the connected runner/.test(document.querySelector('#headline .bar .eyebrow')?.textContent||''),null,{timeout:45000});
  check('native SSE transports actual job progress',requests.some(u=>/\/api\/jobs\/[^/]+\/events/.test(u)));
  check('record recomputes in instrument page',/matches/i.test(await operator.locator('#headline .chip').first().innerText()));
  const page=await ctx.newPage();listen(page);await page.goto(service.url,{waitUntil:'networkidle'});await page.waitForFunction(()=>document.querySelector('#connection-status')?.textContent.includes('CONNECTED'));
  check('completed records remain private until explicit publication',await page.locator('[data-publication]').count()===0);
  await operator.click('#publish');await operator.waitForFunction(()=>document.querySelector('#publish')?.disabled===true);
  check('publish is identified as local handoff',/Published locally/.test(await operator.locator('#publish').innerText()));
  await page.click('#refresh-work');await page.waitForSelector('[data-publication]');check('desk discovers published record without JSON transport',await page.locator('[data-publication]').count()===1);
  check('catalogue matches by source byte identity',/MATCH/.test(await page.locator('#publication-state').innerText()));
  await page.click('[data-publication="0"]');await page.waitForSelector('#qualified-save');
  check('synthetic state survives both interfaces',/Synthetic integration record/.test(await page.locator('#modal-body').innerText()));
  check('primary-cell cost displayed from instrument',!(await page.locator('#modal-body .v').first().innerText()).includes('—'));
  const rec=store.read('records',store.list('records')[0]),before=JSON.stringify(rec);check('exact record identity visible', (await page.locator('#modal-body').innerText()).includes(rec.sha256));
  await page.click('#qualified-save');check('original decision saved',await page.locator('#saved-count').innerText()==='1');
  await page.locator('#modal-body details').first().locator('summary').click();await page.fill('#qualified-rate','1.50');await page.click('#qualified-reprice');
  check('reprice is explicitly a scenario',/Repriced scenario/.test(await page.locator('#qualified-scenario').innerText()));
  check('reprice preserves original record and trial count',JSON.stringify(store.read('records',rec.id))===before&&jobs.list().length===1);
  await page.click('#qualified-save');check('new decision preserves earlier version',await page.locator('#saved-count').innerText()==='2');
  const downloadPromise=page.waitForEvent('download');await page.click('#qualified-export');const download=await downloadPromise;const decisionFile=path.join(OUT,'qualified-decision.json');await download.saveAs(decisionFile);
  const envelope=JSON.parse(fs.readFileSync(decisionFile));Q.verifyDecision(envelope);
  check('reprice links prior decision by checksum',/^[a-f0-9]{64}$/.test(envelope.payload.previous));
  const out=cp.spawnSync(process.execPath,[path.join(ROOT,'compute/scripts/recompute.cjs'),decisionFile],{encoding:'utf8'});check('browser-exported decision verifies in fresh process',out.status===0);
  await page.screenshot({path:path.join(OUT,'qualified-decision.png'),fullPage:true});await page.click('#modal-close');await page.reload({waitUntil:'networkidle'});await page.waitForSelector('[data-publication]');
  check('native reload recovers publications and saved decisions',await page.locator('[data-publication]').count()===1&&await page.locator('#saved-count').innerText()==='2');
  check('private connection token absent from address',new URL(page.url()).hash==='');
  await page.screenshot({path:path.join(OUT,'connected-desk.png'),fullPage:true});
  for(const width of [390,320]){await page.setViewportSize({width,height:844});check('connected desk fits '+width+'px',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  await page.screenshot({path:path.join(OUT,'connected-phone.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:960});
  // A corrupt live publication is held. Previously saved immutable decisions remain valid.
  const published=require('../../hot-aisle/runner/lib/publication-store.cjs').list(store).publications[0];const file=path.join(home,'published',published.publication_id,'bundle.json'),bytes=fs.readFileSync(file);fs.writeFileSync(file,'{}');
  await page.click('#refresh-work');await page.waitForFunction(()=>document.querySelector('#connection-error')?.textContent.includes('1 publication(s) held'));
  check('corrupt publication is not shown as a valid result',await page.locator('[data-publication]').count()===0);fs.writeFileSync(file,bytes);
  await page.locator('[data-saved="0"]').click();check('saved version still verifies independently of current publisher',await page.locator('#qualified-export').isVisible());await page.click('#modal-close');
  await operator.close();await new Promise(resolve=>runner.close(resolve));await page.click('#refresh-work');await page.waitForFunction(()=>document.querySelector('#publication-state')?.textContent.includes('unavailable'));
  check('runner outage is explicit while decisions remain',await page.locator('[data-saved]').count()===2);
  check('no browser script errors',errors.length===0);check('no external application requests',external.length===0);
  await ctx.close();
 }catch(e){errors.push(e.stack);throw e;}
 finally{if(browser)await browser.close();service.server.closeAllConnections();await new Promise(r=>service.server.close(r));if(runner.listening){runner.closeAllConnections();await new Promise(r=>runner.close(r));}await fake.close();fs.rmSync(home,{recursive:true,force:true});fs.writeFileSync(path.join(OUT,'journeys.json'),JSON.stringify({schema:'second-run/seam-browser@1',navigation:'NATIVE_LOCALHOST',checks,passed:checks.length,errors,external_requests:external,hardware_measurement:false},null,2)+'\n');}
 console.log(JSON.stringify({passed:checks.length,errors,external_requests:external},null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
