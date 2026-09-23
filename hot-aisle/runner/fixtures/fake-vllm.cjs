#!/usr/bin/env node
'use strict';
/* A stand-in for `vllm bench serve` used by the local integration environment and the
   test suite. It accepts the same flags the runner emits and writes a result file in
   vLLM's serving-benchmark layout. Every file it writes carries "synthetic": true, so
   nothing produced here can ever be presented as a hardware measurement.

   Behaviour knobs (environment):
     FAKE_VLLM_DELAY_MS   pause before writing, to exercise cancellation and progress
     FAKE_VLLM_FAIL       'corrupt' writes invalid JSON, 'exit' exits 3 without a file
     FAKE_VLLM_MARK       directory that receives one marker file per invocation */
const fs = require('node:fs');
const path = require('node:path');

const args = process.argv.slice(2);
const get = (flag, dflt) => { const i = args.indexOf(flag); return i >= 0 && i + 1 < args.length ? args[i + 1] : dflt; };
const metadata = {};
{ const i = args.indexOf('--metadata'); if (i >= 0) for (let j = i + 1; j < args.length && !args[j].startsWith('--'); j++) { const [k, ...v] = args[j].split('='); metadata[k] = v.join('='); } }

const model = get('--model', 'unknown/model');
const numPrompts = Number(get('--num-prompts', 32));
const concurrency = Number(get('--max-concurrency', 1));
const inputLen = Number(get('--random-input-len', 1024));
const outputLen = Number(get('--random-output-len', 128));
const seed = Number(get('--seed', 1));
const resultDir = get('--result-dir', '.');
const resultFile = get('--result-filename', 'result.json');

let s = (seed * 2654435761 + concurrency * 40503 + 12345) >>> 0;
const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };

function main() {
  if (process.env.FAKE_VLLM_MARK) fs.writeFileSync(path.join(process.env.FAKE_VLLM_MARK, 'run-' + Date.now() + '-' + Math.random().toString(16).slice(2) + '.txt'), args.join(' '));
  const delay = Number(process.env.FAKE_VLLM_DELAY_MS || 0);
  const start = Date.now();
  const tick = () => {
    if (Date.now() - start >= delay) return finish();
    process.stdout.write('progress ' + Math.min(100, Math.round(100 * (Date.now() - start) / delay)) + '%\n');
    setTimeout(tick, Math.min(200, delay));
  };
  tick();
}

function finish() {
  if (process.env.FAKE_VLLM_FAIL === 'exit') { process.stderr.write('simulated failure\n'); process.exit(3); }
  fs.mkdirSync(resultDir, { recursive: true });
  const target = path.join(resultDir, resultFile);
  if (process.env.FAKE_VLLM_FAIL === 'corrupt') { fs.writeFileSync(target, '{"duration": 12.0, "completed": 30, "ttfts": [0.1, 0.2'); return; }
  /* A plausible but plainly synthetic shape: TTFT grows with concurrency, decode is
     per-token, about 2% of requests fail. Deterministic per seed and concurrency. */
  const perTokenS = 0.012 + 0.004 * Math.log2(concurrency);
  const ttfts = [], latencies = [], queue = [], outLens = [], inLens = [], errors = [], texts = [];
  for (let i = 0; i < numPrompts; i++) {
    const fail = rnd() < 0.02;
    const ttft = fail ? 0 : 0.08 + 0.03 * Math.log2(concurrency + 1) + rnd() * 0.05;
    const out = fail ? 0 : Math.max(1, Math.round(outputLen * (0.85 + rnd() * 0.3)));
    ttfts.push(fail ? 0 : +ttft.toFixed(4));
    latencies.push(fail ? 0 : +(ttft + out * perTokenS * (0.9 + rnd() * 0.2)).toFixed(4));
    queue.push(fail ? 0 : +(rnd() * 0.004).toFixed(5));
    outLens.push(out); inLens.push(inputLen); errors.push(fail ? 'synthetic timeout' : ''); texts.push('SYNTHETIC');
  }
  const completed = errors.filter(e => e === '').length;
  const totalOut = outLens.reduce((a, b, i) => a + (errors[i] === '' ? b : 0), 0);
  const okLat = latencies.filter((_, i) => errors[i] === '');
  const duration = +(okLat.reduce((a, b) => a + b, 0) / concurrency * 1.05 + 0.5).toFixed(3);
  const pct = (arr, p) => { const a = arr.filter((_, i) => errors[i] === '').map(x => x * 1000).sort((x, y) => x - y); if (!a.length) return 0; const k = (a.length - 1) * p / 100, lo = Math.floor(k), hi = Math.ceil(k); return +(a[lo] + (a[hi] - a[lo]) * (k - lo)).toFixed(3); };
  const result = {
    synthetic: true,
    date: new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15),
    endpoint_type: 'openai', backend: 'openai', label: 'workload-report',
    model_id: model, tokenizer_id: model, num_prompts: numPrompts,
    ...metadata,
    request_rate: 'inf', burstiness: 1, max_concurrency: concurrency,
    duration, completed, failed: numPrompts - completed,
    total_input_tokens: inLens.reduce((a, b) => a + b, 0), total_output_tokens: totalOut,
    request_throughput: +(completed / duration).toFixed(5), output_throughput: +(totalOut / duration).toFixed(3),
    mean_ttft_ms: pct(ttfts, 50), median_ttft_ms: pct(ttfts, 50), p50_ttft_ms: pct(ttfts, 50), p95_ttft_ms: pct(ttfts, 95), p99_ttft_ms: pct(ttfts, 99),
    mean_e2el_ms: pct(latencies, 50), median_e2el_ms: pct(latencies, 50), p50_e2el_ms: pct(latencies, 50), p95_e2el_ms: pct(latencies, 95), p99_e2el_ms: pct(latencies, 99),
    input_lens: inLens, output_lens: outLens, ttfts, latencies, queue_times: queue, errors, generated_texts: texts,
  };
  fs.writeFileSync(target, JSON.stringify(result));
  process.stdout.write('wrote ' + target + '\n');
}

process.on('SIGTERM', () => process.exit(143));
main();
