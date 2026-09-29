#!/usr/bin/env python3
"""Error-class recurrence across engines from github-issues-deep rows (issues only). stdlib only.
Classes come from the lane's regex on title+body (error_class = first match, error_classes_all = every match).
Spec-decode / prefix-cache clusters here are counted by regex on TITLE only (rows carry no body): lower bound.
Usage: issues_classes.py <issues.jsonl> <out.json>"""
import json, sys, re, statistics as st, collections, datetime, ast, hashlib
src, dst = sys.argv[1], sys.argv[2]
rows = []; h = hashlib.sha256()
with open(src, 'rb') as f:
    for line in f:
        h.update(line); rows.append(json.loads(line))
def dt(s): return datetime.datetime.fromisoformat(s.replace('Z','+00:00')) if s and s not in ('None',) else None
def lst(x):
    if isinstance(x, list): return x
    try: return ast.literal_eval(x) if isinstance(x, str) else []
    except Exception: return []
SPEC = re.compile(r'specul|\bmtp\b|draft[ -_]?model|\beagle\b|medusa|\bngram\b|spec[ _-]?dec|lookahead', re.I)
PFX = re.compile(r'prefix[ _-]?cach|prefix[ _-]?reus|\bapc\b|radix|cache[ _-]?hit', re.I)
engines = sorted(set(r['repo'] for r in rows))
by = collections.defaultdict(list)
for r in rows: by[r['repo']].append(r)
out = dict(input_sha256=h.hexdigest(), n=len(rows), engines={}, classes={}, clusters={})
for e in engines:
    rs = by[e]
    first = collections.Counter(r['error_class'] for r in rs)
    anyc = collections.Counter(c for r in rs for c in set(lst(r['error_classes_all'])))
    closed = [r for r in rs if r['state'] == 'closed']
    out['engines'][e] = dict(issues=len(rs), closed=len(closed), first=first, any=anyc)
# per-class per-engine open-to-close (days), first-match class
cls = collections.defaultdict(lambda: collections.defaultdict(list))
cnt = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    c = r['error_class']; cnt[c][r['repo']] += 1
    a, b = dt(r['created_at']), dt(r['closed_at'])
    if r['state'] == 'closed' and a and b: cls[c][r['repo']].append((b-a).total_seconds()/86400)
    cls[c]['_ALL_open'].append(1) if r['state'] != 'closed' else None
print('engines', {e: out['engines'][e]['issues'] for e in engines})
print('%-24s %s | median days-to-close (closed only) all engines' % ('class (first match)', ' '.join('%-9s' % e.split('/')[1][:9] for e in engines)))
tab = []
for c, cc in sorted(cnt.items(), key=lambda kv: -sum(kv[1].values())):
    allv = [x for e in engines for x in cls[c][e]]
    engs = [e for e in engines if cc[e] > 0]
    row = dict(cls=c, counts={e: cc[e] for e in engines}, n_engines=len(engs), total=sum(cc.values()),
               median_days_close={e: (st.median(cls[c][e]) if cls[c][e] else None) for e in engines},
               median_days_close_all=st.median(allv) if allv else None, closed_n=len(allv),
               share_of_engine={e: cc[e]/out['engines'][e]['issues'] for e in engines})
    tab.append(row)
    print('%-24s %s | %s (n closed %d)' % (c, ' '.join('%-9d' % cc[e] for e in engines), None if not allv else round(st.median(allv),1), len(allv)))
out['classes'] = tab
# completed-only medians and not_planned share by class (state_reason)
print('--- by class: median days to close, state_reason=completed only | share closed as not_planned')
comp = collections.defaultdict(list); npl = collections.Counter(); clo = collections.Counter()
for r in rows:
    if r['state'] != 'closed': continue
    a, b = dt(r['created_at']), dt(r['closed_at'])
    clo[r['error_class']] += 1
    if r['state_reason'] == 'not_planned': npl[r['error_class']] += 1
    if r['state_reason'] == 'completed' and a and b: comp[r['error_class']].append((b-a).total_seconds()/86400)
out['completed_only'] = {}
for c in sorted(clo, key=lambda k: -clo[k]):
    out['completed_only'][c] = dict(median_days_completed=st.median(comp[c]) if comp[c] else None, n_completed=len(comp[c]), closed=clo[c], not_planned=npl[c], not_planned_share=npl[c]/clo[c])
    print('%-24s completed median %s (n %d) | not_planned %d of %d closed = %.1f%%' % (c, None if not comp[c] else round(st.median(comp[c]),1), len(comp[c]), npl[c], clo[c], 100*npl[c]/clo[c]))
# any-match version (issue counted in every class it matches)
anyt = collections.defaultdict(collections.Counter)
for r in rows:
    for c in set(lst(r['error_classes_all'])): anyt[c][r['repo']] += 1
print('--- any-match counts')
for c, cc in sorted(anyt.items(), key=lambda kv: -sum(kv[1].values())):
    print('%-24s %s | total %d engines %d' % (c, ' '.join('%-9d' % cc[e] for e in engines), sum(cc.values()), sum(1 for e in engines if cc[e])))
out['any_match'] = {c: dict(cc) for c, cc in anyt.items()}
# clusters
for name, rx in (('speculative_decoding', SPEC), ('prefix_cache', PFX)):
    cc = collections.Counter(); days = collections.defaultdict(list); op = collections.Counter(); ex = collections.defaultdict(list)
    for r in rows:
        if rx.search(r['title'] or ''):
            cc[r['repo']] += 1
            a, b = dt(r['created_at']), dt(r['closed_at'])
            if r['state'] == 'closed' and a and b: days[r['repo']].append((b-a).total_seconds()/86400)
            else: op[r['repo']] += 1
            if len(ex[r['repo']]) < 2: ex[r['repo']].append(r['url'])
    allv = [x for v in days.values() for x in v]
    out['clusters'][name] = dict(counts=dict(cc), total=sum(cc.values()), still_open=dict(op), median_days_close={e: (st.median(days[e]) if days[e] else None) for e in engines}, median_all=st.median(allv) if allv else None, closed_n=len(allv), examples=dict(ex))
    print('--- cluster', name, dict(cc), 'total', sum(cc.values()), 'open', dict(op), 'median days close', {e: (round(st.median(days[e]),1) if days[e] else None) for e in engines}, 'all', None if not allv else round(st.median(allv),1))
# overall
allc = [(dt(r['closed_at'])-dt(r['created_at'])).total_seconds()/86400 for r in rows if r['state']=='closed' and r['closed_at'] not in (None,'None')]
print('overall closed', len(allc), 'median days', round(st.median(allc),2))
out['overall_median_days_close'] = st.median(allc)
json.dump(out, open(dst,'w'), indent=1, default=str)
