"""Focused browser contract for Cantos's umbrella entry.

Runs only against a locally served build. External navigation is blocked.
"""
from pathlib import Path
import argparse, functools, hashlib, http.server, json, threading, time, traceback
from playwright.sync_api import sync_playwright

p = argparse.ArgumentParser()
p.add_argument('--page', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--browser-executable')
a = p.parse_args()
a.page = a.page.resolve()
a.out.mkdir(parents=True, exist_ok=False)
checks, errors, requests, blocked = [], [], [], []

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

site_root = a.page.parent.parent if a.page.parent.name == 'app' else a.page.parent
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(site_root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{server.server_port}'
url = origin + '/' + a.page.relative_to(site_root).as_posix()

def check(name, passed, detail=''):
    checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
    if not passed:
        raise AssertionError(name + (': ' + detail if detail else ''))

def wait(page, expression):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if page.evaluate(expression): return
        page.wait_for_timeout(20)
    raise AssertionError('Condition not reached: ' + expression)

try:
    with sync_playwright() as pw:
        opts = {'headless': True}
        if a.browser_executable: opts['executable_path'] = a.browser_executable
        browser = pw.chromium.launch(**opts)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
        def route(req):
            if req.request.url.startswith(origin + '/') or req.request.url.startswith('data:'):
                req.continue_()
            else:
                blocked.append(req.request.url); req.abort()
        ctx.route('**/*', route)
        page = ctx.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url) if not r.url.startswith('data:') else None)
        page.goto(url)
        wait(page, 'Boolean(window.CantosPreviewState) && !busy && !document.getElementById("overview-view").hidden')
        check('cold visitor lands on an overview with decision workspace controls hidden',
              page.locator('#overview-view').is_visible() and page.locator('#decision-view').is_hidden()
              and page.locator('.toolbar-actions').is_hidden() and page.locator('.rail-section').first.is_hidden()
              and page.locator('#reset-btn').is_hidden())
        check('overview defines Second Run as three areas and keeps AXM separate',
              page.locator('.program-card').count() == 3
              and 'PRODUCTION' in page.locator('.program-card').nth(1).inner_text()
              and 'INVESTIGATION' in page.locator('.program-card').nth(2).inner_text()
              and page.locator('.foundation-strip').count() == 1)
        check('overview exposes the packet picker, two examples and actual work catalog',
              page.locator('#home-open-btn').is_visible()
              and page.locator('.example-card').count() == 2 and page.locator('.catalog-card').count() == 9)
        check('overview identifies the floor as experimental and circulation as manual',
              'Experimental desk rating from dated public reviews' in page.locator('.catalog-card[data-site-path="floor/index.html"]').inner_text()
              and 'Manually invoked' in page.locator('.catalog-card[data-site-path="circulate/index.html"]').inner_text())

        prefix = '../' if '/app/Cantos.html' in page.evaluate('location.pathname') else ''
        paths = page.locator('[data-site-path]').evaluate_all('(nodes)=>nodes.map(n=>[n.dataset.sitePath,n.getAttribute("href")])')
        local_paths = [path for path, href in paths if path != 'integration/WORK.md']
        links_ok = all(href == prefix + path for path, href in paths)
        files_ok = all((a.page.parent / prefix / path).resolve().is_file() for path in local_paths)
        check('local catalog links resolve from this page and target shipped files', links_ok and files_ok, str(paths))

        before_hash = page.evaluate('C.pack(workspace).then(p=>p.sha256)')
        before_storage = page.evaluate('JSON.stringify(Object.entries(localStorage))')
        page.locator('.trail-card[data-open-workspace="run3"]').click()
        wait(page, '!document.getElementById("decision-view").hidden && !busy')
        check('selecting the current packet opens decision directly without replacement confirmation',
              page.locator('#import-dialog').evaluate('(d)=>!d.open')
              and page.evaluate('C.pack(workspace).then(p=>p.sha256)') == before_hash)
        page.click('#overview-shortcut')
        wait(page, '!document.getElementById("overview-view").hidden')
        check('returning to overview preserves packet and saved-state bytes',
              page.evaluate('C.pack(workspace).then(p=>p.sha256)') == before_hash
              and page.evaluate('JSON.stringify(Object.entries(localStorage))') == before_storage)

        # Importing the already-open packet from home must act as navigation, not replacement.
        payload = page.locator('#run3-packet').text_content()
        with page.expect_file_chooser() as chooser:
            page.locator('#home-open-btn').click()
        chooser.value.set_files({'name': 'same-run3.json', 'mimeType': 'application/json', 'buffer': payload.encode('utf-8')})
        wait(page, '!document.getElementById("decision-view").hidden && !busy')
        check('opening the same packet from overview returns to decision without confirmation',
              page.locator('#import-dialog').evaluate('(d)=>!d.open')
              and page.evaluate('C.pack(workspace).then(p=>p.sha256)') == before_hash)

        # Continue a changed decision through the overview without losing work.
        rate = page.locator('[data-hardware-rate]').first
        rate.fill('9.25')
        page.click('#apply-btn')
        wait(page, '!busy && !CantosPreviewState.current')
        changed_hash = page.evaluate('C.pack(workspace).then(p=>p.sha256)')
        check('the changed scenario has a distinct retained packet', changed_hash != before_hash)
        page.fill('#reviewer', 'Pending reviewer')
        page.click('.brand')
        wait(page, '!document.getElementById("overview-view").hidden')
        page.locator('.case-nav [data-view="decision"]').click()
        wait(page, '!document.getElementById("decision-view").hidden')
        check('overview navigation preserves unsaved decision, pending fields and saved copy',
              page.evaluate('C.pack(workspace).then(p=>p.sha256)') == changed_hash
              and page.locator('[data-hardware-rate]').first.input_value() == '9.25'
              and page.locator('#reviewer').input_value() == 'Pending reviewer'
              and page.evaluate('JSON.stringify(Object.entries(localStorage))') == before_storage)
        # Run 3 is intentionally large enough to exceed Chromium's per-origin
        # localStorage quota; save/resume is verified using the synthetic packet.
        page.click('#overview-shortcut')
        wait(page, '!document.getElementById("overview-view").hidden')
        page.locator('.example-card[data-open-workspace="example"]').click()
        wait(page, 'document.getElementById("import-dialog").open')
        page.click('#confirm-import')
        wait(page, '!busy && !document.getElementById("decision-view").hidden && document.querySelectorAll(".task-cell").length===48')
        saved_hash = page.evaluate('C.pack(workspace).then(p=>p.sha256)')
        page.click('#save-btn')
        wait(page, 'persist === true')
        saved_bytes = page.evaluate('localStorage.getItem(KEY)')
        page.click('#overview-shortcut')
        check('returning home leaves explicitly saved bytes unchanged', page.evaluate('localStorage.getItem(KEY)') == saved_bytes)
        page.reload()
        wait(page, 'Boolean(window.CantosPreviewState) && !busy && !document.getElementById("decision-view").hidden')
        check('a saved decision resumes on reload with its exact packet',
              page.evaluate('C.pack(workspace).then(p=>p.sha256)') == saved_hash
              and page.evaluate('localStorage.getItem(KEY)') == saved_bytes)
        page.click('#overview-shortcut')
        wait(page, '!document.getElementById("overview-view").hidden')
        for width in (1440, 390, 320):
            page.set_viewport_size({'width': width, 'height': 900})
            check(f'overview fits {width}px viewport', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.screenshot(path=str(a.out / f'overview-{width}.png'), full_page=True)

        # Validate the standalone app route too when the build includes it.
        sibling = a.page.parent / 'app' / 'Cantos.html'
        if sibling.is_file() and sibling.resolve() != a.page:
            page.evaluate('localStorage.removeItem(KEY)')
            page.goto(origin + '/app/Cantos.html')
            wait(page, 'Boolean(window.CantosPreviewState) && !document.getElementById("overview-view").hidden')
            app_paths = page.locator('[data-site-path]').evaluate_all('(nodes)=>nodes.map(n=>[n.dataset.sitePath,n.getAttribute("href")])')
            check('standalone app links use their parent-relative route',
                  all(href == '../' + path for path, href in app_paths), str(app_paths))
        check('no uncaught page errors or external requests', not errors and not blocked, repr(errors + blocked))
        browser.close()
except Exception:
    errors.append(traceback.format_exc())
finally:
    server.shutdown()
report = {'page': str(a.page), 'page_sha256': hashlib.sha256(a.page.read_bytes()).hexdigest(),
          'checks': checks, 'errors': errors, 'requests': requests, 'blocked': blocked,
          'all_pass': bool(checks) and all(c['passed'] for c in checks) and not errors and not blocked,
          'scope': 'Overview navigation and local entry behavior; no external navigation or production qualification.'}
(a.out / 'OVERVIEW.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['all_pass'] else 1)
