"""Render seven UTC days of listed probes and distinct delivered attempts."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from probe import ROOT, config, key, stamp

VALID = {'available', 'out_of_capacity', 'out_of_stock'}
DOTS = {'available': '#166534', 'out_of_capacity': '#c2410c', 'out_of_stock': '#c2410c',
        'create_failed': '#be123c', 'ssh_failed': '#7e22ce', 'unknown': '#475569'}


def dt(value):
    return datetime.fromisoformat(stamp(value).replace('Z', '+00:00'))


def aggregate(records, targets, now):
    now = dt(now)
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=167)
    grid = {key(r): [dict(yes=0, valid=0, unknown=0, slots=set(), attempts=[]) for _ in range(168)] for r in targets}
    excluded = defaultdict(int)
    first_api = {}
    seen = set()
    for row in records:
        k = key(row)
        when = dt(row['ts'])
        if row.get('synthetic') is True:
            excluded['synthetic'] += 1
            continue
        # Older API observations establish when sampling began even if they no
        # longer contribute to this week's availability denominator.
        if when <= now and row.get('layer') == 'listed' and row.get('method') == 'api':
            first_api[k] = min(first_api.get(k, when), when)
        if not start <= when <= now:
            excluded['outside window'] += 1
            continue
        layer = row.get('layer')
        # Existing console-create success explicitly records SSH time. No listing
        # is promoted to a delivery just because its provisioned flag is true.
        if layer is None and row.get('method') == 'console-create':
            layer = 'delivered'
        if layer == 'listed' and row.get('method') != 'api':
            layer = None
        if layer not in ('listed', 'delivered'):
            excluded['legacy listing/note (not scheduled API probes)'] += 1
            continue
        cells = grid.setdefault(k, [dict(yes=0, valid=0, unknown=0, slots=set(), attempts=[]) for _ in range(168)])
        cell = cells[int((when - start).total_seconds() // 3600)]
        if layer == 'listed':
            cell['slots'].add(when.minute // 15)
            outcome = row.get('outcome')
            cell['valid'] += outcome in VALID
            cell['yes'] += outcome == 'available'
            cell['unknown'] += outcome not in VALID
        else:
            attempt_id = row.get('attempt_id')
            if attempt_id:
                if attempt_id in seen:
                    raise ValueError('duplicate delivered attempt ID')
                seen.add(attempt_id)
            outcome = row.get('outcome', 'unknown')
            if outcome == 'available' and not (row.get('ssh_reached') is True or
                    (row.get('method') == 'console-create' and row.get('provisioned') is True and
                     type(row.get('time_to_ssh_s')) in (int, float) and row['time_to_ssh_s'] >= 0)):
                outcome = 'unknown'
            cell['attempts'].append(outcome if outcome in DOTS else 'unknown')
    for k, cells in grid.items():
        first_slot = int((first_api[k] - start).total_seconds() // 900) if k in first_api else 168 * 4
        for i, cell in enumerate(cells):
            elapsed = 4 if i < 167 else now.minute // 15 + 1
            cell['not_sampled'] = min(elapsed, max(0, first_slot - i * 4))
            cell['expected'] = elapsed - cell['not_sampled']
    return start, now, grid, dict(excluded)


def render(records, targets, now):
    start, now, grid, excluded = aggregate(records, targets, now)
    summary = [f'Availability: {stamp(start.isoformat())} through {stamp(now.isoformat())}',
               '168 UTC hour columns; current hour partial. Listed = yes / valid API probes.',
               'Unknowns excluded from fraction. Missed = empty elapsed 15-minute slots from each row\'s first API observation.',
               'Earlier hours/slots are not sampled; rows without API observations are entirely not sampled.',
               'Delivered = confirmed SSH / real create attempts; separate denominator.',
               'Historical manual listings are excluded from API fractions. No new results asserted.', '']
    width, height = 425 + 168 * 23, 100 + 65 * len(grid)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-labelledby="chart-title"><title id="chart-title">Listed availability by UTC hour; delivered attempts are dots</title>']
    for i in range(168):
        hour = start + timedelta(hours=i)
        if hour.hour == 0 or i == 0:
            svg.append(f'<text x="{425+i*23}" y="22">{hour:%b %d}</text>')
        if hour.hour % 3 == 0:
            svg.append(f'<text x="{425+i*23}" y="43">{hour:%H}</text>')
    details = []
    for ri, (k, cells) in enumerate(sorted(grid.items())):
        label = ' / '.join(map(str, k[:3])) + f' / {k[3]} GPU'
        y = 60 + ri * 65
        totals = dict(yes=0, valid=0, unknown=0, missed=0, not_sampled=0, delivered=0, attempts=0)
        svg.append(f'<text x="8" y="{y+17}">{escape(label)}</text>')
        for i, cell in enumerate(cells):
            expected = cell['expected']
            missed = expected - len(cell['slots'])
            attempts = cell['attempts']
            delivered_count = attempts.count('available')
            for name in ('yes', 'valid', 'unknown'):
                totals[name] += cell[name]
            totals['missed'] += missed
            totals['not_sampled'] += cell['not_sampled']
            totals['attempts'] += len(attempts)
            totals['delivered'] += delivered_count
            hour = start + timedelta(hours=i)
            fraction = cell['yes'] / cell['valid'] if cell['valid'] else None
            color = '#94a3b8' if fraction is None else f'hsl({round(20+140*fraction)},65%,43%)'
            caption = (f'{hour:%Y-%m-%d %H:00 UTC}: listed {cell["yes"]}/{cell["valid"]}; '
                       f'unknown {cell["unknown"]}; missed {missed}/{expected} slots; '
                       f'delivered {delivered_count}/{len(attempts)}; outcomes: {", ".join(attempts) or "none"}')
            if cell['not_sampled']:
                caption += f'; not sampled {cell["not_sampled"]} slots'
            x = 425+i*23
            svg.append(f'<rect x="{x}" y="{y}" width="21" height="23" fill="{color}"><title>{escape(label+": "+caption)}</title></rect>')
            for di, outcome in enumerate(attempts[:8]):
                svg.append(f'<circle cx="{x+4+(di%4)*5}" cy="{y+30+(di//4)*7}" r="2.5" fill="{DOTS[outcome]}"><title>{escape(outcome)}</title></circle>')
            if len(attempts) > 8:
                svg.append(f'<text x="{x}" y="{y+51}">+{len(attempts)-8}</text>')
            if cell['valid'] or cell['unknown'] or attempts:
                details.append(f'<tr><td>{escape(label)}</td><td>{escape(caption)}</td></tr>')
                summary.append(label + ' | ' + caption)
        line = (f'listed {totals["yes"]}/{totals["valid"]}; unknown {totals["unknown"]}; '
                f'missed {totals["missed"]}; delivered {totals["delivered"]}/{totals["attempts"]}')
        svg.append(f'<text class="small" x="8" y="{y+37}">{escape(line)}</text>')
        unsampled = f'not sampled {totals["not_sampled"]} slots'
        svg.append(f'<text class="small" x="8" y="{y+51}">{unsampled}</text>')
        summary.append('TOTAL ' + label + ' | ' + line + '; ' + unsampled)
    svg.append('</svg>')
    summary.extend(['', 'Excluded records: ' + json.dumps(excluded, sort_keys=True)])
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Availability ledger — seven UTC days</title><style>
:root{color-scheme:light dark;--bg:#f8fafc;--fg:#172033;--line:#cbd5e1}*{box-sizing:border-box}
body{margin:0;padding:24px;font:16px/1.55 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
h1{font-size:28px;margin:0}p{max-width:90ch}.scroll{overflow:auto;border:1px solid var(--line);padding:8px}
svg text{fill:var(--fg);font:12px system-ui,sans-serif}svg .small{font-size:10px}circle{stroke:var(--bg);stroke-width:.6}
table{border-collapse:collapse;font-size:13px;width:100%}td,th{border:1px solid var(--line);padding:8px;text-align:left}
@media(prefers-color-scheme:dark){:root{--bg:#0f172a;--fg:#e2e8f0;--line:#475569}}
</style><h1>Availability ledger</h1>'''
    page += f'<p>{escape(summary[0])}. Current UTC hour is partial.</p>'
    page += '<p>Missed slots start at each row\'s first API observation, including unknown observations. Earlier hours and quarter-hour slots are labelled not sampled. A row with no API observations has no missed slots.</p>'
    page += '<p>Cells: orange 0% → green 100% listed, divided by valid API probes. Grey means unknown, missed or not sampled. Unknowns never count as stockouts. Hover cells for denominators, or read the table below.</p><p>Dots: green = reached SSH; orange = capacity/stock refusal; red = create failed; purple = SSH failed; slate = unknown. Delivered uses its own attempt denominator. More than eight attempts in an hour show an overflow count.</p><p>Listing is not a reservation or proof of account quota. Historical manual listings are retained in the source ledger and excluded from API fractions.</p>'
    page += '<div class="scroll" tabindex="0" aria-label="Scrollable seven-day heatmap">' + ''.join(svg) + '</div>'
    page += '<h2>Observed hours and denominators</h2><table><tr><th>Provider / SKU / region / GPUs</th><th>UTC hour and counts</th></tr>' + ''.join(details) + '</table>'
    page += '<p>Excluded records: ' + escape(json.dumps(excluded, sort_keys=True)) + '</p></html>\n'
    return page, '\n'.join(summary) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=ROOT / 'observations.jsonl')
    p.add_argument('--config', type=Path, default=ROOT / 'probes.json')
    p.add_argument('--html', type=Path, default=ROOT / 'heatmap.html')
    p.add_argument('--summary', type=Path, default=ROOT / 'heatmap.txt')
    p.add_argument('--now', default=stamp())
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        import unittest
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT), 'test_availability.py')).wasSuccessful() else 1
    try:
        if len({a.input.resolve(), a.config.resolve(), a.html.resolve(), a.summary.resolve()}) != 4:
            raise ValueError('input, config and output paths must differ')
        records = [json.loads(line) for line in a.input.read_text(encoding='utf-8').splitlines() if line.strip()]
        page, summary = render(records, config(a.config)['probes'], a.now)
        a.html.write_text(page, encoding='utf-8')
        a.summary.write_text(summary, encoding='utf-8')
        print(f'Wrote {a.html.name} and {a.summary.name}; {len(records)} source records')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
