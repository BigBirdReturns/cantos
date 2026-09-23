'use strict';
/* Hot Aisle adapter. Reads the account's teams, allocations, state, balance and the
   on-demand price of each VM type through the public API documented at
   https://admin.hotaisle.app/api/docs/ . Read-only: it never provisions, deletes or
   powers anything. The token is taken from HOTAISLE_API_TOKEN or the official CLI's
   ~/.hotaisle/config.json and is never written anywhere by this module. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DEFAULT_BASE = 'https://admin.hotaisle.app/api';

function tokenFromEnvironment() {
  if (process.env.HOTAISLE_API_TOKEN) return process.env.HOTAISLE_API_TOKEN;
  const file = path.join(os.homedir(), '.hotaisle', 'config.json');
  try { const cfg = JSON.parse(fs.readFileSync(file, 'utf8')); if (cfg.api_token) return cfg.api_token; } catch (e) { /* no config */ }
  return null;
}

function maskEmail(email) {
  if (typeof email !== 'string' || !email.includes('@')) return null;
  const [local, domain] = email.split('@');
  return local.slice(0, 1) + '***@' + domain;
}

class HotAisle {
  constructor({ token = tokenFromEnvironment(), baseUrl = process.env.HOTAISLE_API_BASE || DEFAULT_BASE, fetchImpl = globalThis.fetch } = {}) {
    if (!token) throw new Error('No Hot Aisle API token. Set HOTAISLE_API_TOKEN or log in with the official CLI.');
    this.header = token.startsWith('Token ') ? token : 'Token ' + token;
    this.base = baseUrl.replace(/\/$/, '');
    this.fetch = fetchImpl;
  }
  async get(p) {
    const res = await this.fetch(this.base + p, { headers: { Authorization: this.header, Accept: 'application/json', 'User-Agent': 'workload-report-runner/2.2' } });
    if (res.status === 401 || res.status === 403) throw new Error('Hot Aisle API refused the token (' + res.status + ').');
    if (!res.ok) throw new Error('Hot Aisle API ' + p + ' returned ' + res.status + '.');
    return res.json();
  }
  user() { return this.get('/user/'); }
  teams() { return this.get('/teams/'); }
  vms(team) { return this.get('/teams/' + encodeURIComponent(team) + '/virtual_machines/'); }
  vmState(team, vm) { return this.get('/teams/' + encodeURIComponent(team) + '/virtual_machines/' + encodeURIComponent(vm) + '/state/'); }
  availableVMs(team) { return this.get('/teams/' + encodeURIComponent(team) + '/virtual_machines/available/'); }
  balance(team) { return this.get('/teams/' + encodeURIComponent(team) + '/balance/'); }
  bareMetal(team) { return this.get('/teams/' + encodeURIComponent(team) + '/bare_metal/'); }

  /* Produces the environment object the planner consumes. Retrieved facts are
     labelled retrieved; anything the API did not return is listed under unknown
     rather than guessed. */
  async inspect({ team } = {}) {
    const unknown = [];
    const me = await this.user();
    const teams = asArray(me.teams).map(t => ({ handle: t.handle, name: t.name, roles: t.effective_roles || t.roles || [] }));
    const handle = team || (teams[0] && teams[0].handle);
    if (!handle) throw new Error('The token belongs to no team.');
    const [vms, types, balance] = await Promise.all([this.vms(handle).catch(e => { unknown.push('virtual machines: ' + e.message); return []; }), this.availableVMs(handle).catch(e => { unknown.push('VM types and prices: ' + e.message); return []; }), this.balance(handle).catch(e => { unknown.push('balance: ' + e.message); return null; })]);
    const priceFor = specs => {
      const g = gpuSummary(specs);
      const match = asArray(types).find(t => { const tg = gpuSummary(t.Specs || t.specs); return tg.count === g.count && tg.model === g.model; });
      return match && Number.isFinite(match.OnDemandPrice) && g.count ? { gpu_hour_usd: +(match.OnDemandPrice / 100 / g.count).toFixed(4), allocation_hour_usd: +(match.OnDemandPrice / 100).toFixed(2), minimum_minutes: match.MinimumReservationMinutes, retrieved: true } : null;
    };
    const allocations = [];
    for (const vm of asArray(vms)) {
      let state = null;
      try { state = (await this.vmState(handle, vm.deployment_id || vm.name)).state; } catch (e) { unknown.push('state of ' + (vm.name || vm.deployment_id)); }
      const gpus = gpuSummary(vm);
      allocations.push({ kind: 'vm', deployment_id: vm.deployment_id || null, name: vm.name || null, description: vm.description || null, ip: vm.ip_address || null, ssh: vm.ssh_access ? { host: vm.ssh_access.dns_name || vm.ssh_access.ip_address, port: vm.ssh_access.port || 22 } : null, gpus, state, price: priceFor(vm) || (unknown.push('price for ' + (vm.name || vm.deployment_id)), null) });
    }
    return {
      adapter: 'hotaisle', retrieved_at: new Date().toISOString(), base_url: this.base,
      user: { name: me.user ? me.user.name : null, email: maskEmail(me.user && me.user.email) },
      team: handle, teams, allocations,
      balance: balance ? { available_usd: cents(balance.available_balance), hourly_usd: cents(balance.hourly_rate), estimated_runout: balance.estimated_runout_time || null, active_vms: balance.virtual_machine_count ?? null } : null,
      vm_types: asArray(types).map(t => ({ gpus: gpuSummary(t.Specs || t.specs), on_demand_allocation_hour_usd: Number.isFinite(t.OnDemandPrice) ? +(t.OnDemandPrice / 100).toFixed(2) : null, minimum_minutes: t.MinimumReservationMinutes ?? null, available: t.Quantity ?? null })),
      unknown,
    };
  }
}

function asArray(x) { return Array.isArray(x) ? x : x && Array.isArray(x.results) ? x.results : x && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).length === 0 ? [] : x ? [x] : []; }
function cents(v) { return Number.isFinite(v) ? +(v / 100).toFixed(2) : null; }
function gpuSummary(specs) {
  const g = asArray(specs && specs.gpus);
  const count = g.reduce((n, x) => n + (x.count || 0), 0);
  const model = g.length ? [...new Set(g.map(x => [x.manufacturer, x.model].filter(Boolean).join(' ')))].join(' + ') : null;
  return { count, model };
}

module.exports = { HotAisle, tokenFromEnvironment, DEFAULT_BASE, gpuSummary, maskEmail };
