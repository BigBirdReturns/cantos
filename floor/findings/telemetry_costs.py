#!/usr/bin/env python3
"""Run 3 (and Run 1) cost windows recomputed from retained files. stdlib only. Prints every figure with its inputs."""
import json, os, datetime as D
R = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'hot-aisle', 'campaign', 'results'))
def t(s): return D.datetime.fromisoformat(s.replace('Z', '+00:00'))
def mins(a, b): return (t(b) - t(a)).total_seconds() / 60
HA, DO = 2.99, 4.41
lt = {a: json.load(open(os.path.join(R, a, 'ledger-times.json'))) for a in ('run3-smoke-a-t0', 'run3-scored-a-t0', 'run3-scored-a-t1', 'run3-scored-n-t0')}
acc = {'a0': 4336, 'a1': 4292, 'smoke': 458, 'n0': 4280}
det = {a: json.load(open(os.path.join(R, a, 'detailed.json'))) for a in ('run3-scored-a-t0', 'run3-scored-a-t1', 'run3-scored-n-t0')}
req, ssh, rel = '2026-09-24T00:08:55Z', '2026-09-24T00:10:57Z', '2026-09-24T02:52:29Z'
prov = mins(req, ssh)
print('HA seat: request->ssh %.2f min (%.0f s); request->delete %.2f min = %.4f h' % (prov, prov*60, mins(req, rel), mins(req, rel)/60))
for a in ('run3-smoke-a-t0', 'run3-scored-a-t0', 'run3-scored-a-t1'):
    x = lt[a]; print(a, 'script %.2f min; work %.2f min; ssh->ready %.2f min' % (mins(x['t_script_start'], x['t_script_end']), mins(x['t_work_start'], x['t_work_end']), mins(x['t_ssh'], x['t_ready'])))
w0 = mins(lt['run3-scored-a-t0']['t_script_start'], lt['run3-scored-a-t0']['t_script_end'])
w1 = mins(lt['run3-scored-a-t1']['t_script_start'], lt['run3-scored-a-t1']['t_script_end'])
ws = mins(lt['run3-smoke-a-t0']['t_script_start'], lt['run3-smoke-a-t0']['t_script_end'])
print('A/T0 own window w/o provisioning %.2f min -> $%.4f -> $%.4f/1k' % (w0, w0/60*HA, w0/60*HA/acc['a0']*1000))
print('A/T0 own window + provisioning %.2f min -> $%.4f -> $%.4f/1k   (=$0.74 published)' % (w0+prov, (w0+prov)/60*HA, (w0+prov)/60*HA/acc['a0']*1000))
print('A/T1 own window w/o provisioning %.2f min -> $%.4f -> $%.4f/1k ; +prov -> $%.4f/1k' % (w1, w1/60*HA, w1/60*HA/acc['a1']*1000, (w1+prov)/60*HA/acc['a1']*1000))
dur = det['run3-scored-a-t0']['duration']; a_s = acc['a0']/dur
print('in-page: accepted/s %.7f (4336/%.4f s); $%.4f/1k = 2.99/3600/acc_per_s*1000' % (a_s, dur, HA/3600/a_s*1000))
tot = acc['a0']+acc['a1']+acc['smoke']; whole = mins(req, rel)/60*HA
print('whole seat: %.4f h -> $%.4f; accepted %d -> $%.4f/1k' % (mins(req, rel)/60, whole, tot, whole/tot*1000))
lb0 = mins(lt['run3-scored-a-t0']['t_ssh'], lt['run3-scored-a-t0']['t_work_end']); lb1 = mins(lt['run3-scored-a-t1']['t_ssh'], lt['run3-scored-a-t1']['t_work_end'])
print('ledger lower bound A/T0 (ssh->work_end) %.2f min $%.4f -> $%.4f/1k ; A/T1 %.2f min $%.4f -> $%.4f/1k' % (lb0, lb0/60*HA, lb0/60*HA/acc['a0']*1000, lb1, lb1/60*HA, lb1/60*HA/acc['a1']*1000))
print('seat time split: smoke script %.1f min, A/T0 script %.1f, A/T1 script %.1f; sum %.1f of %.1f min = %.1f%% ; idle/setup remainder %.1f min' % (ws, w0, w1, ws+w0+w1, mins(req, rel), 100*(ws+w0+w1)/mins(req, rel), mins(req, rel)-(ws+w0+w1)))
sc = w0+w1
print('scored-only share of billed seat: %.1f%%' % (100*sc/mins(req, rel)))
# DO
x = lt['run3-scored-n-t0']; nreq, nrel = '2026-09-24T04:08:03Z', '2026-09-24T05:17:52Z'
print('DO: request->ssh %.0f s; ssh->ready %.2f min; request->release %.2f min -> $%.4f -> $%.4f/1k; script %.2f min -> $%.4f/1k' % (mins(nreq, x['t_ssh'])*60, mins(x['t_ssh'], x['t_ready']), mins(nreq, nrel), mins(nreq, nrel)/60*DO, mins(nreq, nrel)/60*DO/acc['n0']*1000, mins(x['t_script_start'], x['t_script_end']), mins(x['t_script_start'], x['t_script_end'])/60*DO/acc['n0']*1000))
dn = det['run3-scored-n-t0']['duration']; print('DO in-page-basis (rate/acc_per_s over replay duration %.1f s): $%.4f/1k' % (dn, DO/3600/(acc['n0']/dn)*1000))
print('DO request->active 56 s (04:08:03 -> 04:08:59 per obs row 24); request->ssh %.0f s' % (mins(nreq, x['t_ssh'])*60))
# breakeven
print('break-even H100 $/h vs HA $0.7434: exact %.4f; RUN3-RESULTS rounded %.2f' % (0.7434/(1.1989/4.41), 4.41*0.74/1.20))
# gap ratios
print('HA cheaper: as-run 1-0.7434/1.199 = %.1f%%; public 1.99 vs 3.39: %.1f%%; public 2.99 vs 3.39: %.1f%%; vs DO skypilot 6.74 -> H100 $/1k %.4f' % (100*(1-0.7434/1.199), 100*(1-0.4948/0.9216), 100*(1-0.7434/0.9216), 0.9216*6.74/3.39))
print('HA 1.99->2.99: +%.2f%% ; $/1k %.4f -> %.4f' % (100*(2.99/1.99-1), 0.4948, 0.7434))
print('Run1: HA c64 $0.0717 vs DO c32 $0.1526 -> HA cheaper %.1f%% ; whole-run LB 0.9248 vs 0.9802 -> %.1f%%' % (100*(1-0.0717/0.1526), 100*(1-0.9248/0.9802)))
