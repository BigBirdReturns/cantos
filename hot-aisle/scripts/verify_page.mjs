#!/usr/bin/env node
/* Browser journeys against the actual page revision. Two passes:
     static     the page opened from disk: zero network, no console errors, the shipped
                demonstration record is recomputed and matches, sample import works
     connected  the page served by the runner in demo mode: connect, prepare, approve,
                run to completion, record recomputed in-browser, revalidate three ways,
                reload and reattach, start-and-cancel keeps completed trials
   Needs playwright + chromium (npm i playwright && npx playwright install chromium).
   Prints a JSON result; exits 1 on any failure. */
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const page_path = path.join(root, 'index.html');
const results = { static: {}, connected: {}, failures: [] };
const check = (scope, name, ok, detail) => { results[scope][name] = ok ? 'pass' : 'FAIL' + (detail ? ': ' + detail : ''); if (!ok) results.failures.push(scope + ':' + name); };

async function newPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [], external = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { const u = r.url(); if (!u.startsWith('file:') && !/^https?:\/\/(127\.0\.0\.1|localhost)/.test(u)) external.push(u); });
  return { page, errors, external };
}

async function staticPass(browser) {
  const { page, errors, external } = await newPage(browser);
  await page.goto(pathToFileURL(page_path).href);
  await page.waitForTimeout(600);
  check('static', 'no_console_errors', errors.length === 0, errors.join(' | '));
  check('static', 'zero_external_requests', external.length === 0, external.join(' '));
  check('static', 'six_breakeven_tiles', (await page.locator('#breaktable .tile').count()) === 6);
  const chip = await page.locator('#headline .chip').first().innerText().catch(() => '');
  check('static', 'demo_record_recomputed_matches', /RECOMPUTED HERE · MATCHES/i.test(chip), chip);
  check('static', 'demo_record_marked_synthetic', /SYNTHETIC EXAMPLE/i.test(await page.locator('#headline .bar .eyebrow').innerText()));
  check('static', 'rail_not_connected', /not connected/i.test(await page.locator('#rail-state').innerText()));
  check('static', 'demo_record_not_badged_qualified', !/^QUALIFIED$/i.test((await page.locator('#headline .bar .chip').last().innerText()).trim()));
  check('static', 'section_says_no_gpu_measured', /no GPU was measured/i.test(await page.locator('#record-eyebrow').innerText()));
  check('static', 'no_machine_paths_in_page', !new RegExp('Program' + ' Files|[A-Z]:\\\\').test(await page.content()));
  check('static', 'runner_url_box_hidden_until_asked', await page.locator('#setup').isHidden());
  await page.click('#open-setup'); await page.waitForTimeout(100);
  check('static', 'setup_panel_opens', await page.locator('#runner-url').isVisible());
  await page.fill('#runner-url', 'not a url at all'); await page.click('#connect'); await page.waitForTimeout(200);
  check('static', 'bad_runner_url_refused_without_fetch', /full URL/.test(await page.locator('#connect-msg').innerText()) && external.length === 0);
  await page.fill('#runner-url', 'http://127.0.0.1:1'); await page.click('#connect');
  await page.waitForFunction(() => /No runner answered/.test(document.getElementById('connect-msg').textContent), null, { timeout: 8000 });
  check('static', 'unreachable_runner_plain_message', /node runner\/bin\/workload\.cjs serve/.test(await page.locator('#connect-msg').innerText()));
  check('static', 'connect_button_recovers', !(await page.locator('#connect').isDisabled()) && /Connect runner/.test(await page.locator('#connect').innerText()));
  check('static', 'rail_reports_unreachable', /unreachable/i.test(await page.locator('#rail-state').innerText()));
  await page.click('#open-setup');
  await page.click('#example'); await page.waitForTimeout(1000);
  check('static', 'sample_two_cards', (await page.locator('#report .resultcard').count()) === 2);
  check('static', 'sample_comparison', /lower cost/i.test(await page.locator('#report .comparison strong').innerText().catch(() => '')));
  check('static', 'download_enabled', !(await page.locator('#save-html').isDisabled()));
  await page.click('#theme'); await page.waitForTimeout(200);
  check('static', 'dark_toggle', (await page.evaluate(() => document.documentElement.dataset.theme)) === 'dark');
  check('static', 'theme_persisted', (await page.evaluate(() => { try { return localStorage.getItem('theme'); } catch (e) { return 'unavailable'; } })) !== 'light');
  await page.click('#copy'); await page.waitForTimeout(100);
  check('static', 'copy_confirms', /Copied|Saved as/.test(await page.locator('#copy').innerText()));
  await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(200);
  const layout = await page.evaluate(() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.right>innerWidth+1&&!e.closest('.scrollx')&&!e.closest('.top nav');}).map(e=>({tag:e.tagName,id:e.id,class:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,100)})).slice(0,30)}));
  if(layout.scrollWidth>layout.width+1){results.layout=layout;fs.mkdirSync('instrument-browser-qa',{recursive:true});await page.screenshot({path:'instrument-browser-qa/overflow.png',fullPage:true});}
  check('static', 'phone_no_horizontal_scroll', layout.scrollWidth <= layout.width + 1);
  check('static', 'phone_nav_visible', await page.locator('.top nav').isVisible());
  check('static', 'phone_ledger_scrolls_not_clips', await page.evaluate(() => { const w = document.querySelector('#headline .scrollx'); return !!w && getComputedStyle(w).overflowX === 'auto' && w.scrollWidth >= w.clientWidth; }));
  for (const width of [320,360,768]) { await page.setViewportSize({width,height:844}); await page.waitForTimeout(50); check('static','responsive_content_'+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)); }
  await page.close();
}

function startRunner() {
  return new Promise((resolve, reject) => {
    const home = fs.mkdtempSync(path.join(os.tmpdir(), 'wl-journey-'));
    const child = spawn(process.execPath, [path.join(root, 'runner', 'bin', 'workload.cjs'), 'serve', '--demo', '--port', '0'], { env: { ...process.env, WORKLOAD_HOME: home, FAKE_VLLM_DELAY_MS: '0' }, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    child.stdout.on('data', d => { out += d; const m = out.match(/listening at (http:\/\/127\.0\.0\.1:\d+)/); if (m) resolve({ child, url: m[1], home }); });
    child.stderr.on('data', d => { out += d; });
    child.on('exit', code => reject(new Error('runner exited ' + code + ': ' + out)));
    setTimeout(() => reject(new Error('runner did not start: ' + out)), 15000);
  });
}

async function connectedPass(browser) {
  const runner = await startRunner();
  try {
    const { page, errors } = await newPage(browser);
    await page.goto(runner.url + '/');
    await page.waitForFunction(() => /^Runner · connected/i.test(document.getElementById('rail-state').textContent), null, { timeout: 15000 });
    check('connected', 'auto_connect_on_loopback', true);
    { const t = await page.locator('#rail-env').innerText(); check('connected', 'environment_in_rail', /MI300X/.test(t), t); }
    await page.click('#open-plan'); await page.waitForSelector('#preview');
    await page.fill('#f-concurrency', '1, 8'); await page.fill('#f-repeats', '1'); await page.fill('#f-num_prompts', '24');
    await page.click('#preview');
    await page.waitForSelector('#approve-start', { timeout: 15000 });
    const hash = await page.locator('#instrument .kv .v.mono').innerText();
    check('connected', 'plan_hash_shown', /^[a-f0-9]{64}$/.test(hash.trim()), hash);
    check('connected', 'command_preview', /--save-result --save-detailed/.test(await page.locator('#instrument .term').innerText()));
    await page.click('#approve-start');
    await page.waitForFunction(() => document.querySelector('#headline .bar .eyebrow') && /from the connected runner/i.test(document.querySelector('#headline .bar .eyebrow').textContent), null, { timeout: 60000 });
    check('connected', 'job_completed_record_shown', true);
    const chip = await page.locator('#headline .chip').first().innerText();
    check('connected', 'record_recomputed_in_browser', /MATCHES/i.test(chip), chip);
    check('connected', 'record_rows', (await page.locator('#headline .ledger tbody tr').count()) === 2);
    await page.waitForSelector('#rv-price');
    await page.click('#rv-price'); await page.waitForSelector('.conclusions');
    check('connected', 'revalidate_price_recomputed', /recomputed/i.test(await page.locator('.conclusions').innerText()));
    check('connected', 'revalidate_price_no_measurement', !(await page.locator('#rv-plan').count()));
    await page.fill('#rv-traffic-v', '1, 8, 64'); await page.click('#rv-traffic'); await page.waitForSelector('#rv-plan', { timeout: 10000 });
    check('connected', 'revalidate_traffic_minimal_plan_64', /concurrency 64 × 1/.test(await page.locator('#rv-plan').innerText()));
    await page.click('#rv-runtime'); await page.waitForFunction(() => /superseded/i.test((document.querySelector('.conclusions') || {}).textContent || ''), null, { timeout: 10000 });
    check('connected', 'revalidate_runtime_superseded', true);
    await page.click('#rv-plan'); await page.waitForSelector('#preview');
    check('connected', 'minimal_plan_prefills_form', (await page.inputValue('#f-concurrency')) === '1, 8');
    // reload: the page must reattach to the same durable state
    await page.reload(); await page.waitForFunction(() => /^Runner · connected/i.test(document.getElementById('rail-state').textContent), null, { timeout: 15000 });
    await page.waitForFunction(() => /from the connected runner/i.test((document.querySelector('#headline .bar .eyebrow') || {}).textContent || ''), null, { timeout: 15000 });
    check('connected', 'reload_reattaches_record', true);
    // start a slow job and cancel it: completed trials survive
    await page.click('#open-plan'); await page.waitForSelector('#preview');
    await page.fill('#f-concurrency', '1, 8, 32'); await page.fill('#f-repeats', '1');
    await page.evaluate(() => { window.__slow = true; });
    await page.route('**/api/jobs', async (route, req) => { if (req.method() === 'POST') { const body = JSON.parse(req.postData()); body.target.env = { FAKE_VLLM_DELAY_MS: '1500' }; await route.continue({ postData: JSON.stringify(body) }); } else await route.continue(); });
    await page.click('#preview'); await page.waitForSelector('#approve-start'); await page.click('#approve-start');
    await page.waitForSelector('#cancel', { timeout: 15000 });
    await page.waitForFunction(() => /completed/.test((document.querySelector('#instrument .ledger') || {}).textContent || ''), null, { timeout: 20000 });
    await page.click('#cancel');
    await page.waitForFunction(() => /cancelled/i.test(document.getElementById('rail-job').textContent), null, { timeout: 20000 });
    const jobs = await (await fetch(runner.url + '/api/jobs')).json();
    const cancelled = jobs.find(j => j.state === 'cancelled');
    check('connected', 'cancel_keeps_completed_trials', !!cancelled && cancelled.trials.completed >= 1 && cancelled.trials.completed < 3, JSON.stringify(cancelled && cancelled.trials));
    check('connected', 'no_console_errors', errors.length === 0, errors.join(' | '));
    await page.close();
  } finally { runner.child.kill(); }
}

/* PLAYWRIGHT_MODULE lets a local run point at any installed copy (a file URL to its index.mjs). */
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch();
try {
  await staticPass(browser);
  await connectedPass(browser);
} catch (e) { results.failures.push('exception: ' + e.message); }
finally { await browser.close(); }
results.page_sha256 = (await import('node:crypto')).createHash('sha256').update(fs.readFileSync(page_path)).digest('hex');
results.checked_at = new Date().toISOString();
console.log(JSON.stringify(results, null, 2));
process.exit(results.failures.length ? 1 : 0);
