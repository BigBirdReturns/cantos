#!/usr/bin/env python3
"""Recurring incident title patterns across provider status pages (clustermax-challenge/retrospective/incidents/*.json).
Keyword classes are ours, applied to titles (multi-label). Windows differ per provider (coverage_start/end), so counts are
not rates; 'providers' = distinct providers with >=1 incident in the class is the recurrence measure.
Usage: incident_patterns.py <incidents_dir> <out.json>"""
import json, sys, re, glob, os, collections, statistics as st, datetime, hashlib
d, dst = sys.argv[1], sys.argv[2]
CL = collections.OrderedDict([
 ('network / connectivity / DNS / latency', r'network|connectivity|packet|latency|\bdns\b|\bbgp\b|routing|vpn|internet|transit|\bwan\b|\blan\b|infiniband|fabric'),
 ('storage / volumes / object storage / filesystem', r'storage|volume|\bs3\b|object|filesystem|file system|\bnfs\b|lustre|vast|disk|bucket'),
 ('control plane / API / provisioning / instance create', r'\bapi\b|control plane|provision|deploy|instance|create|launch|orchestrat|scheduling|\bvm\b|virtual machine|server creation'),
 ('console / dashboard / website / UI', r'console|dashboard|website|\bui\b|portal|web app|panel|login page'),
 ('authentication / login / SSO / account', r'auth|login|log in|sign[ -]?in|\bsso\b|account|\biam\b|token'),
 ('compute / GPU / node / host hardware', r'\bgpu|node|host|hardware|compute|\bcpu\b|hypervisor|rack|xid|chassis'),
 ('degraded performance / elevated errors / latency (generic)', r'degrad|elevated|increased error|errors|slow|delay|performance|intermittent'),
 ('outage / unavailable / down (generic)', r'outage|unavailable|\bdown\b|not working|unreachable|failure|failed|disrupt'),
 ('kubernetes / slurm / cluster services', r'kubernetes|\bk8s\b|slurm|cluster|\bkube'),
 ('billing / payments / invoices', r'billing|payment|invoice|charge'),
 ('inference / model serving / endpoints', r'inference|serverless|endpoint|model|llm'),
 ('scheduled or emergency maintenance', r'maintenance|upgrade|patch|migration'),
])
files = sorted(f for f in glob.glob(os.path.join(d, '*.json')) if not os.path.basename(f).startswith('RAW'))
def dt(s):
    try: return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception: return None
acc = {k: dict(providers=set(), n=0, n_nonmaint=0, dur=[]) for k in CL}
prov_rows = []; total = 0; totalnm = 0; shas = {}
for f in files:
    raw = open(f, 'rb').read(); shas[os.path.basename(f)] = hashlib.sha256(raw).hexdigest()
    j = json.loads(raw); p = j['provider'].lower()
    inc = j['incidents']; nm = [i for i in inc if not i['is_maintenance']]
    prov_rows.append((os.path.basename(f), p, len(inc), len(nm), j['coverage_start'], j['coverage_end']))
    total += len(inc); totalnm += len(nm)
    for i in inc:
        t = i['title'] or ''
        for k, rx in CL.items():
            if re.search(rx, t, re.I):
                a = acc[k]; a['providers'].add(p); a['n'] += 1
                if not i['is_maintenance']:
                    a['n_nonmaint'] += 1
                    s, e = dt(i['started_utc']), dt(i['resolved_utc'] or '')
                    if s and e and e >= s: a['dur'].append((e - s).total_seconds() / 3600)
print('files', len(files), 'providers with >=1 incident', sum(1 for r in prov_rows if r[2] > 0), 'incidents', total, 'non-maintenance', totalnm)
print('%-58s %9s %6s %8s %14s' % ('class', 'providers', 'n', 'n_nonmnt', 'median h (nonmaint, resolved)'))
out = []
for k, a in sorted(acc.items(), key=lambda kv: -len(kv[1]['providers'])):
    md = st.median(a['dur']) if a['dur'] else None
    print('%-58s %9d %6d %8d %14s (n=%d)' % (k, len(a['providers']), a['n'], a['n_nonmaint'], None if md is None else round(md, 2), len(a['dur'])))
    out.append(dict(cls=k, providers=len(a['providers']), provider_names=sorted(a['providers']), n=a['n'], n_nonmaint=a['n_nonmaint'], median_hours_nonmaint=md, n_resolved=len(a['dur'])))
# most repeated normalized exact-ish titles
norm = collections.defaultdict(set); cnt = collections.Counter()
for f in files:
    j = json.load(open(f, encoding='utf-8')); p = j['provider'].lower()
    for i in j['incidents']:
        t = re.sub(r'\b[A-Za-z]{2,}-?[a-z]*\d+[a-z0-9-]*\b', '', i['title'] or ''); t = re.sub(r'[\d]+', '#', t).lower(); t = re.sub(r'\s+', ' ', t).strip(' -:')
        norm[t].add(p); cnt[t] += 1
print('--- titles (numbers/region ids stripped) shared by >=3 providers')
top = sorted(((len(v), cnt[t], t) for t, v in norm.items() if len(v) >= 3), reverse=True)[:15]
for a, b, t in top: print(a, 'providers', b, 'incidents:', t)
json.dump(dict(files=shas, providers=prov_rows, classes=out, shared_titles=top, incidents=total, nonmaintenance=totalnm), open(dst, 'w'), indent=1)
