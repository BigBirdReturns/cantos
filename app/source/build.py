"""Rebuild a locally qualified candidate; no deployment or network access."""
from pathlib import Path
import hashlib, json, argparse
P=Path(__file__).resolve().parent
arg=argparse.ArgumentParser();arg.add_argument('--out',type=Path,default=P.parent/'Cantos.html');args=arg.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
owner=P.parent/'owner-research-core/research-core-1.0.2.js'
assert sha(owner)=='2bfcac9b188d56c91c4d98831e5bfae2dc2b06ed99632eb093d912eb1214d170'
assert (P/'research-core.js').read_bytes()==owner.read_bytes(), 'Generated core differs from owner candidate'
html=(P/'index.template.html').read_text(encoding='utf-8')
for key,name in [('STYLE','style.css'),('CORE','research-core.js'),('FOUNDATION','foundation.js'),('APP','app.js')]:
 assert html.count('/*'+key+'*/')==1
 html=html.replace('/*'+key+'*/',(P/name).read_text(encoding='utf-8'))
for banned in ['D:/Projects','D:\\Projects','S:/Scratch','S:\\Scratch','ssh_host','enc1-gpuvm','<iframe','https://fonts.','cdn.jsdelivr']:
 assert banned not in html, banned
args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(html,encoding='utf-8',newline='\n')
manifest={'artifact':args.out.name,'sha256':sha(args.out),'status':'local revised candidate; not deployed or council-reaccepted',
 'core_owner':'owner-research-core/research-core-1.0.2.js','core_sha256':sha(owner),
 'prior_core_sha256':sha(P.parent/'owner-research-core/1.0.0-original.js'),
 'prior_native_app_unchanged':True,'source_files':{p.name:sha(p) for p in sorted(P.iterdir()) if p.suffix in ['.js','.css','.html','.py','.cjs']}}
args.out.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
