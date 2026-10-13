#!/usr/bin/env python3
"""The downloadable handover package beside the Chapek page: the zip extracts, every file hashes as its
manifest says, the packaged page is the published page, the packaged record is the page's record, and the
entry point resolves against this checkout (dry run). Standard library only; no native procedure is executed.
Usage: python -B compute/chapek/tests/package_check.py [out-dir]"""
import hashlib, json, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
ZIP = HERE / 'Cantos-Chapek-Seat-package.zip'
PAGE = HERE / 'index.html'
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='chapek-package-'))
OUT.mkdir(parents=True, exist_ok=True)
EXTRACT = OUT / 'extract'
if EXTRACT.exists():
    import shutil
    shutil.rmtree(EXTRACT)
EXTRACT.mkdir()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks = []
def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

check('zip present and under 20 MB', ZIP.is_file() and ZIP.stat().st_size < 20 * 1024 * 1024)
with zipfile.ZipFile(ZIP) as z:
    names = z.namelist()
    check('zip has a single top-level folder', len({n.split('/')[0] for n in names}) == 1)
    check('zip entries are plain files of known types', all(re.search(r'\.(html|json|jsonl|py|md)$', n) for n in names))
    z.extractall(EXTRACT)
pkg = EXTRACT / names[0].split('/')[0]
manifest = json.loads((pkg / 'MANIFEST.json').read_text(encoding='utf-8'))
check('every manifest file is present and hashes as listed', all((pkg / rel).is_file() and sha(pkg / rel) == info['sha256'] for rel, info in manifest['files'].items()))
check('no file outside the manifest', {p.relative_to(pkg).as_posix() for p in pkg.rglob('*') if p.is_file()} == set(manifest['files']) | {'MANIFEST.json'})
check('the packaged page is the published page', sha(pkg / 'Cantos-Chapek-Seat.html') == sha(PAGE) == manifest['page_sha256'])
page = PAGE.read_text(encoding='utf-8')
seed = re.search(r'<script id="seed-packet" type="application/json">([\s\S]*?)</script>', page)
record = json.loads((pkg / 'Cantos-Chapek-Seat.packet.json').read_text(encoding='utf-8'))
check('the packaged record is the page\'s record', seed and json.loads(seed.group(1))['sha256'] == record['sha256'] == manifest['record_sha256'])
check('the page links the package download', 'href="' + manifest['download'] + '"' in page and manifest['download'].endswith('/compute/chapek/' + ZIP.name))
pins = manifest['checkout']['pins']
drift = {name for name, rel in (('work', 'integration/work.py'), ('change_owner', 'integration/change_owner.cjs'), ('research_handoff', 'integration/research_handoff.py'), ('research_owner', 'integration/research_owner.py'), ('task_changes', 'integration/task_changes.py')) if sha(ROOT / rel) != pins[name]}
check('this checkout carries the runner bytes the package was qualified against (' + ', '.join(sorted(drift)) + ')', not drift)
dry = subprocess.run([sys.executable, '-I', 'next.py', '--checkout', str(ROOT), '--dry-run'], cwd=pkg, capture_output=True, text=True, encoding='utf-8')
check('next.py resolves against this checkout (dry run)', dry.returncode == 0 and 'Resolved request' in dry.stdout and '<checkout>' not in Path(dry.stdout.split('Resolved request: ', 1)[1].splitlines()[0]).read_text(encoding='utf-8'))
report = {'status': 'PASS', 'checks': checks, 'count': len(checks), 'zip_sha256': sha(ZIP), 'page_sha256': sha(PAGE), 'record_sha256': record['sha256'], 'scope': 'Package integrity and binding to the published page in this checkout; the entry point in dry run. No native procedure executed, no network.'}
(OUT / 'package-results.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
