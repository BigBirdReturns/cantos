"""Project the reviewed comparison source through the existing public allowlist.

Read a committed private owner checkout; never copy its tree wholesale. Public
inputs, collector rights mappings and frozen shortlist remain from public base.
"""
from pathlib import Path
import argparse, hashlib, io, json, subprocess, zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '22ce99cdfccd18b77897a641312ed576b6f24cb2'
ARCHIVE = 'public/open-compute/open-compute-workbench.zip'
OLD_SHA = '449ec4d453ee4c272c867148c0f12ff7b9890726845923bc991980960e274624'
PREFIX = 'cantos/open-compute-ledger/'

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    args.commit = git(args.owner, 'rev-parse', args.commit).decode().strip()
    base = git(ROOT, 'show', BASE + ':' + ARCHIVE)
    assert hashlib.sha256(base).hexdigest() == OLD_SHA
    with zipfile.ZipFile(io.BytesIO(base)) as z:
        files = {name:z.read(name) for name in z.namelist()}
    before = dict(files)
    sources = ['engine/engine.py', 'engine/comparisons.py', 'workbench.html', 'workbench.css', 'workbench.js', 'comparisons/frozen-vllm.zip']
    tracked = git(args.owner, 'ls-tree', '-r', '--name-only', args.commit, '--', 'open-compute-ledger/engine/native_maintainer').decode().splitlines()
    sources += [p.removeprefix('open-compute-ledger/') for p in tracked if p.endswith(('.py', '/SOURCE.json'))]
    provenance = json.loads(files[PREFIX+'PUBLIC-SOURCES.json'])
    for path in sources:
        raw = git(args.owner, 'show', args.commit + ':open-compute-ledger/' + path)
        provenance['sources'][path] = hashlib.sha256(raw).hexdigest()
        if path == 'engine/engine.py':
            for a,b in [(b'"mi210": "octo-w02", "rtx8000": "octo-w03"',b'"mi210": "local-run-b", "rtx8000": "local-run-c"'),
                        (b'providers.get(arm, "octo-w01")',b'providers.get(arm, "local-profile-a")'),
                        (b'("fourb", "octo-w01"), ("zeropointsix", "octo-w03")',b'("fourb", "local-profile-a"), ("zeropointsix", "local-run-c")')]:
                assert raw.count(a) == 1, a
                raw = raw.replace(a,b)
        if path == 'workbench.html':
            raw = raw.replace(b'<a href="open-compute-ledger-kit.zip">Download kit</a>', b'<a href="comparisons/frozen-vllm.zip" download>Example comparison</a>')
            raw = raw.replace('href="index.html#b" class="text-button">All provider records →'.encode(), 'href="inputs/providers/ratings.json" class="text-button">Provider records (JSON) →'.encode())
        files[PREFIX+path] = raw
    provenance.update(prior_public_commit=BASE, workbench_source_commit=args.commit,
        comparison_scope='Data-only native verdict review, immutable policy reanalysis, frozen real evidence; no new empirical measurement.')
    files[PREFIX+'PUBLIC-SOURCES.json'] = encoded(provenance)
    notes = b'''\n\n## Review a serving change\n\nStart the workbench and select **Open the real vLLM experiment**. The first view\nrevalidates 192 retained requests and source-bound application grades: 21/96\naccepted on each side, incomparable under the original 80% requirement. No\ninference or uploaded code executes. Import one comparison ZIP exported with\n`maintainer.py export-comparison --analysis ANALYSIS --out comparison.zip`.\n\nNative pass/regression/incomparable/error is authoritative. Policy reanalysis\nkeeps the original capture and creates a permanently labelled post-hoc history\nentry. Export the analysis JSON for that edition and the original evidence ZIP\nseparately. Price assumptions remain modeled; actual cost and whole-system energy\nremain unknown. The catalog is separately available for scoped configuration\nscreening. Broader application, operational and economic coverage remains open.\n'''
    files[PREFIX+'WORKBENCH.md'] = files[PREFIX+'WORKBENCH.md'].rstrip() + notes
    manifest = json.loads(files[PREFIX+'MANIFEST.json'])
    manifest['files'] = {k.removeprefix('cantos/'):hashlib.sha256(v).hexdigest() for k,v in sorted(files.items()) if k != PREFIX+'MANIFEST.json'}
    files[PREFIX+'MANIFEST.json'] = encoded(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):
            info = zipfile.ZipInfo(name,(2026,11,18,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    data = out.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    (ROOT/ARCHIVE).write_bytes(data)
    (ROOT/'public/open-compute/SHA256SUMS.txt').write_text(digest+'  open-compute-workbench.zip\n',encoding='utf-8')
    receipt = {'schema':'cantos.comparison-workbench-release/1','owner_source_commit':args.commit,
        'prior_published_commit':BASE,'prior_archive_sha256':OLD_SHA,'archive':'open-compute-workbench.zip',
        'sha256':digest,'bytes':len(data),'files':len(files),
        'changed_public_members':[p for p in sorted(files) if files[p] != before.get(p)],
        'includes_private_operational_closure':False,'new_inference_requests':0}
    (ROOT/'public/open-compute/WORKBENCH-RELEASE.json').write_bytes(encoded(receipt))
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
