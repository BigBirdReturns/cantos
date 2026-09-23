'use strict';
/* Builds and executes `vllm bench serve` for one cell of an approved plan. The runner
   never invents a benchmark: it drives vLLM's own serving benchmark with pinned
   export flags and retrieves the exact result bytes. */
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const EXPORT_FLAGS = ['--save-result', '--save-detailed', '--percentile-metrics', 'ttft,tpot,itl,e2el', '--metric-percentiles', '50,95,99'];

function metadataArgs(identity, cell, plan) {
  const pairs = {
    model_revision: identity.model_revision,
    precision: identity.precision,
    tokenizer_revision: identity.tokenizer_revision,
    workload_id: identity.workload_id,
    cache_policy: identity.cache_policy,
    runtime_digest: identity.runtime_digest,
    load_profile: loadProfile(plan.workload, cell),
    plan_sha256: plan.sha256,
    cell: 'c' + cell.concurrency + '-r' + cell.repeat,
  };
  const out = ['--metadata'];
  for (const [k, v] of Object.entries(pairs)) if (v !== undefined && v !== null && v !== '') out.push(k + '=' + String(v).replace(/\s+/g, '_'));
  return out.length > 1 ? out : [];
}

function loadProfile(w, cell) {
  return ['dataset=' + w.dataset, 'in=' + w.input_len, 'out=' + w.output_len, 'prompts=' + w.num_prompts, 'concurrency=' + cell.concurrency, 'rate=' + w.request_rate, 'seed=' + w.seed].join(';');
}

function buildArgs(plan, cell, resultDir, resultFile) {
  const w = plan.workload;
  const args = [
    '--backend', w.backend || 'openai',
    '--base-url', w.base_url,
    '--model', w.model,
    '--dataset-name', w.dataset,
    '--num-prompts', String(w.num_prompts),
    '--max-concurrency', String(cell.concurrency),
    '--request-rate', String(w.request_rate),
    '--seed', String(w.seed + cell.repeat),
    '--label', 'workload-report',
    ...EXPORT_FLAGS,
    '--result-dir', resultDir,
    '--result-filename', resultFile,
  ];
  if (w.dataset === 'random') args.push('--random-input-len', String(w.input_len), '--random-output-len', String(w.output_len));
  if (w.served_model_name) args.push('--served-model-name', w.served_model_name);
  if (w.tokenizer) args.push('--tokenizer', w.tokenizer);
  if (w.endpoint) args.push('--endpoint', w.endpoint);
  args.push(...metadataArgs(plan.identity, cell, plan));
  return args;
}

function shellQuote(s) {
  return /^[A-Za-z0-9_./:=,+@%-]+$/.test(s) ? s : "'" + String(s).replace(/'/g, "'\\''") + "'";
}

function commandString(command, args) {
  return [...command, ...args].map(shellQuote).join(' ');
}

/* Executes one benchmark. exec 'local' spawns on this machine (the runner lives on
   the VM). exec 'ssh' spawns through OpenSSH with BatchMode so no prompt can hang,
   and pulls the result file back with scp. A cancellation kills the process we own;
   for ssh the remote shell is started with a HUP/TERM trap so the benchmark dies with
   the session instead of continuing to bill. */
function execute({ target, plan, cell, workDir, signal, onLine }) {
  const resultFile = 'cell-c' + cell.concurrency + '-r' + cell.repeat + '.json';
  const command = target.vllm_command || ['vllm', 'bench', 'serve'];
  const remoteDir = target.remote_dir || '/tmp/workload-report';
  const args = buildArgs(plan, cell, target.exec === 'ssh' ? remoteDir : workDir, resultFile);
  const preview = commandString(command, args);
  return new Promise((resolve, reject) => {
    let child;
    const tail = [];
    const line = s => { for (const l of String(s).split(/\r?\n/)) if (l.trim()) { tail.push(l); if (tail.length > 40) tail.shift(); if (onLine) onLine(l); } };
    if (target.exec === 'ssh') {
      const remote = 'mkdir -p ' + shellQuote(remoteDir) + ' && sh -c ' + shellQuote('trap "kill 0" HUP TERM INT; ' + preview);
      const sshArgs = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ServerAliveInterval=15'];
      if (target.ssh_port) sshArgs.push('-p', String(target.ssh_port));
      sshArgs.push((target.ssh_user ? target.ssh_user + '@' : '') + target.host, remote);
      child = spawn('ssh', sshArgs, { stdio: ['ignore', 'pipe', 'pipe'], env: process.env });
    } else {
      child = spawn(command[0], [...command.slice(1), ...args], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...(target.env || {}) }, cwd: workDir });
    }
    child.stdout.on('data', line);
    child.stderr.on('data', line);
    const abort = () => { try { child.kill('SIGTERM'); } catch (e) { /* already gone */ } setTimeout(() => { try { child.kill('SIGKILL'); } catch (e) { /* gone */ } }, 3000).unref(); };
    if (signal) { if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true }); }
    child.on('error', err => reject(Object.assign(new Error('Could not start benchmark: ' + err.message), { preview })));
    child.on('close', async code => {
      if (signal) signal.removeEventListener('abort', abort);
      if (signal && signal.aborted) return reject(Object.assign(new Error('Cancelled.'), { cancelled: true, preview }));
      if (code !== 0) return reject(Object.assign(new Error('Benchmark exited with code ' + code + '. ' + tail.slice(-3).join(' | ')), { preview, exitCode: code }));
      try {
        const local = path.join(workDir, resultFile);
        if (target.exec === 'ssh') await scp(target, remoteDir + '/' + resultFile, local);
        if (!fs.existsSync(local)) throw new Error('Benchmark exited 0 but wrote no result file.');
        resolve({ bytes: fs.readFileSync(local), preview, exitCode: code, localPath: local });
      } catch (e) { reject(Object.assign(e, { preview })); }
    });
  });
}

function scp(target, remote, local) {
  return new Promise((resolve, reject) => {
    const args = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new'];
    if (target.ssh_port) args.push('-P', String(target.ssh_port));
    args.push((target.ssh_user ? target.ssh_user + '@' : '') + target.host + ':' + remote, local);
    const child = spawn('scp', args, { stdio: 'ignore' });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve() : reject(new Error('scp exited with code ' + code)));
  });
}

module.exports = { buildArgs, commandString, execute, EXPORT_FLAGS, loadProfile, shellQuote };
