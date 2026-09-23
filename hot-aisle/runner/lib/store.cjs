'use strict';
/* Durable, file-backed state. Jobs, records and retained evidence live under one
   directory so a reconnecting client, a new process or a different interface
   recovers the same objects. Writes are atomic (temp file + rename). */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

function home() {
  return process.env.WORKLOAD_HOME || path.join(os.homedir(), '.workload-report');
}

class Store {
  constructor(root = home()) {
    this.root = root;
    for (const d of ['jobs', 'records', 'evidence', 'published']) fs.mkdirSync(path.join(root, d), { recursive: true });
  }
  file(kind, id) {
    if (!/^[A-Za-z0-9._-]{1,120}$/.test(id)) throw new Error('Invalid identifier.');
    return path.join(this.root, kind, id + '.json');
  }
  write(kind, id, value) {
    const target = this.file(kind, id);
    const tmp = target + '.' + process.pid + '.' + crypto.randomBytes(4).toString('hex') + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n');
    fs.renameSync(tmp, target);
    return target;
  }
  read(kind, id) {
    const target = this.file(kind, id);
    if (!fs.existsSync(target)) return null;
    return JSON.parse(fs.readFileSync(target, 'utf8'));
  }
  list(kind) {
    const dir = path.join(this.root, kind);
    return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).sort();
  }
  remove(kind, id) {
    const target = this.file(kind, id);
    if (fs.existsSync(target)) fs.unlinkSync(target);
  }
  /* Raw benchmark bytes are retained privately, keyed by their SHA-256, so a record's
     source commitments can be re-verified later without re-running hardware. */
  saveEvidence(bytes) {
    const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
    const target = path.join(this.root, 'evidence', sha256 + '.json');
    if (!fs.existsSync(target)) {
      const tmp = target + '.' + process.pid + '.tmp';
      fs.writeFileSync(tmp, bytes);
      fs.renameSync(tmp, target);
    }
    return { sha256, bytes: bytes.length, path: target };
  }
  evidencePath(sha256) {
    if (!/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid evidence hash.');
    const target = path.join(this.root, 'evidence', sha256 + '.json');
    return fs.existsSync(target) ? target : null;
  }
  newId(prefix) {
    const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
    return prefix + '-' + stamp + '-' + crypto.randomBytes(3).toString('hex');
  }
}

module.exports = { Store, home };
