"""Cantos floor gates. Usage: python run_floor_gates.py <preview_dir> [--packets <dir>] [--skip-controller]"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, datetime
from pathlib import Path

BUILD = Path(r'D:\Projects\Organs\AXM\axm-tools\sessions\field-niches-20260927\cantos-ben-build-20260928')
DEF_PACKETS = BUILD / 'council-review' / 'astra'
CTRL = BUILD / 'preview-v0.2.0' / 'verification'

def run(cmd, cwd=None, env=None, timeout=900):
    e = dict(os.environ); e['PYTHONIOENCODING'] = 'utf-8'
    if env: e.update(env)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=e, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def native(pd):
    files = [pd/'source'/'foundation.test.cjs', pd/'tests'/'regression.test.cjs']
    rc, out = run(['node', '--test'] + [str(f) for f in files])
    def n(k):
        m = re.findall(r'^\D*\b' + k + r'\s+(\d+)\s*$', out, re.M)
        return int(m[-1]) if m else 0
    res = {'tests': n('tests'), 'pass': n('pass'), 'fail': n('fail')}
    res['ok'] = rc == 0 and res['fail'] == 0 and res['tests'] > 0
    return res, out

def browser(pd, packets, vdir, tmp):
    out = tmp / 'browser'  # script requires a fresh, nonexistent dir
    rc, log = run([sys.executable, str(pd/'tests'/'browser_regressions.py'), '--page', str(pd/'Cantos.html'), '--packets', str(packets), '--out', str(out)])
    f = out / 'BROWSER.json'
    if not f.exists(): return {'checks': 0, 'all_pass': False, 'errors': ['no BROWSER.json: ' + log[-500:]]}, None
    j = load(f); shutil.copy2(f, vdir/'BROWSER.json')
    return {'checks': len(j['checks']), 'all_pass': bool(j['all_pass']) and all(c.get('pass') for c in j['checks']), 'errors': j['errors']}, j

def controller(pd, vdir, tmp):
    stage = tmp / 'controller'; (stage/'candidate').mkdir(parents=True)
    shutil.copy2(pd/'Cantos.html', stage/'candidate'/'Cantos.html')
    res = {}
    for name, sub, key in (('mobile_check.py', 'mobile-final', 'mobile'), ('visual_check_v2.py', 'visual', 'workspace')):
        # The controller scripts were written when the cold load was the synthetic invoice example.
        # The staged copy (never the original) selects that example through the rail first; the checks themselves are untouched.
        src = (CTRL/name).read_text(encoding='utf-8')
        pat = "wait(page,'Boolean(window.CantosPreviewState)')"
        assert pat in src, name
        helper = '''def _select_example(page):
    wait(page,'Boolean(window.CantosPreviewState) && !busy')
    page.locator('[data-open-workspace="example"]').click();wait(page,'document.getElementById("import-dialog").open')
    page.click('#confirm-import');wait(page,'!busy && !pendingImport && document.querySelectorAll(".task-cell").length===48')

'''
        i = src.index('def wait(')
        src = src[:i] + helper + src[i:]
        src = src.replace(pat, pat + ';_select_example(page)')
        (stage/name).write_text(src, encoding='utf-8')
        rc, log = run([sys.executable, str(stage/name)], cwd=stage)
        f = stage / sub / 'CHECKS.json'
        if not f.exists():
            res[key] = ({'checks': 0, 'all_pass': False, 'errors': [log[-500:]]}, None); continue
        j = load(f); shutil.copy2(f, vdir/('CHECKS-%s.json' % key))
        res[key] = ({'checks': len(j['checks']), 'all_pass': bool(j['all_pass']), 'errors': j.get('errors', [])}, j)
    return res

def overflow(pd):
    from playwright.sync_api import sync_playwright
    cases, fails, perrs = 0, [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in (1440, 390, 320):
            ctx = b.new_context(viewport={'width': w, 'height': 900}); pg = ctx.new_page()
            pg.on('pageerror', lambda e, w=w: perrs.append('%d: %s' % (w, e)))
            pg.goto((pd/'Cantos.html').resolve().as_uri()); pg.wait_for_timeout(400)
            for v in ('decision', 'evidence', 'architecture'):
                pg.evaluate("view('%s')" % v); pg.wait_for_timeout(200)
                sw = pg.evaluate('document.documentElement.scrollWidth'); cases += 1
                if sw > w: fails.append({'view': v, 'width': w, 'scrollWidth': sw})
            ctx.close()
        b.close()
    return {'cases': cases, 'failures': fails}, perrs

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('preview_dir'); ap.add_argument('--packets', default=str(DEF_PACKETS)); ap.add_argument('--skip-controller', action='store_true')
    a = ap.parse_args()
    pd = Path(a.preview_dir).resolve(); packets = Path(a.packets).resolve()
    vdir = pd / 'verification'; vdir.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='cantos-gates-'))
    page = (pd/'Cantos.html').read_bytes()
    ok = True; lines = []
    nat, _ = native(pd); ok &= nat['ok']
    lines.append('native   : %d tests, %d pass, %d fail  %s' % (nat['tests'], nat['pass'], nat['fail'], 'PASS' if nat['ok'] else 'FAIL'))
    br, _ = browser(pd, packets, vdir, tmp); ok &= br['all_pass']
    lines.append('browser  : %d checks, %d errors  %s' % (br['checks'], len(br['errors']), 'PASS' if br['all_pass'] else 'FAIL'))
    mob = ws = None
    if a.skip_controller:
        lines.append('mobile   : skipped'); lines.append('workspace: skipped')
    else:
        c = controller(pd, vdir, tmp); mob, ws = c['mobile'][0], c['workspace'][0]
        ok &= mob['all_pass'] and ws['all_pass']
        lines.append('mobile   : %d checks  %s' % (mob['checks'], 'PASS' if mob['all_pass'] else 'FAIL'))
        lines.append('workspace: %d checks  %s' % (ws['checks'], 'PASS' if ws['all_pass'] else 'FAIL'))
    ov, perrs = overflow(pd); ok &= (not ov['failures'] and ov['cases'] == 9 and not perrs)
    lines.append('overflow : %d cases, %d failures, %d page errors  %s' % (ov['cases'], len(ov['failures']), len(perrs), 'PASS' if not ov['failures'] and not perrs and ov['cases'] == 9 else 'FAIL'))
    rep = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'preview_dir': str(pd),
           'page_sha256': hashlib.sha256(page).hexdigest(), 'page_bytes': len(page),
           'native': {k: nat[k] for k in ('tests', 'pass', 'fail')}, 'browser': br, 'mobile': mob, 'workspace': ws,
           'overflow': ov, 'page_errors': perrs, 'skipped_controller': a.skip_controller, 'status': 'PASS' if ok else 'FAIL'}
    (vdir/'VERIFIED.json').write_text(json.dumps(rep, indent=2) + '\n', encoding='utf-8')
    print('\n'.join(lines)); print('sha256 %s  %d bytes' % (rep['page_sha256'][:12], rep['page_bytes'])); print('STATUS ' + rep['status'])
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
