#!/usr/bin/env python3
"""Build the single-file public page and self-contained offline/MCP kit."""
from pathlib import Path
import json,hashlib,zipfile,argparse,re
ROOT=Path(__file__).resolve().parents[1]
MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

def human_date(iso):
    """22 Sep 2026 style, locale independent; fails loudly on a malformed catalogue date."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',iso):raise ValueError('Catalogue date is not ISO: '+repr(iso))
    y,m,d=(int(x) for x in iso.split('-'))
    if not 1<=m<=12:raise ValueError('Catalogue month out of range: '+iso)
    return f'{d} {MONTHS[m-1]} {y}'

def schedule_options(catalog):
    """The default schedule is the review date; every later announced effective date is offered too.
    Deriving both from the catalogue keeps engine.priceAt (asOf >= reviewedOn) satisfiable after a price review."""
    reviewed=catalog['reviewedOn']
    future=sorted({s['effectiveOn'] for o in catalog['offers'] for s in o.get('schedules',[]) if s['effectiveOn']>reviewed})
    options=[f'<option value="{reviewed}">{human_date(reviewed)} snapshot</option>']
    options+=[f'<option value="{d}">{human_date(d)} announced</option>' for d in future]
    return ''.join(options)

def build():
    text=(ROOT/'template.html').read_text(encoding='utf-8')
    catalog_text=(ROOT/'data/catalog.json').read_text(encoding='utf-8');catalog=json.loads(catalog_text)
    replacements={'STYLE':(ROOT/'style.css').read_text(encoding='utf-8'),'CATALOG':catalog_text,'SAMPLE':(ROOT/'tests/fixtures.json').read_text(encoding='utf-8'),'DONOR':(ROOT/'adapters/workload-engine.cjs').read_text(encoding='utf-8'),'QUALIFIED':(ROOT/'adapters/qualified-engine.cjs').read_text(encoding='utf-8'),'ENGINE':(ROOT/'engine.cjs').read_text(encoding='utf-8'),'APP':(ROOT/'app.js').read_text(encoding='utf-8'),'REVIEWED_DATE':human_date(catalog['reviewedOn']),'AS_OF_OPTIONS':schedule_options(catalog)}
    for name,body in replacements.items():
        marker='/*'+name+'*/'
        if text.count(marker)!=1:raise ValueError('Template slot missing or duplicated: '+name)
        # JSON/JS must not close their containing script element.
        if name not in ('STYLE',):body=body.replace('</script','<\\/script')
        text=text.replace(marker,body)
    (ROOT/'index.html').write_text(text,encoding='utf-8',newline='\n')
    allow=['index.html','template.html','style.css','app.js','engine.cjs','data/catalog.json','adapters/workload-engine.cjs','adapters/qualified-engine.cjs','adapters/instrument.cjs','adapters/workload-report-v2.html','scripts/connect.cjs','scripts/recompute.cjs','scripts/build.py','scripts/review_prices.py','README.md','LICENSE','PROVENANCE.json','METHOD.md','QUALIFICATION.json','tests/fixtures.json','tests/test_core.cjs','tests/test_bridge.cjs','tests/test_browser.py','tests/test_prices.py']
    allow += ['scripts/materials.cjs', 'scripts/material_feeds.py', 'materials/registry.json', 'materials/observations.json', 'materials/README.md', 'tests/test_materials.cjs', 'tests/test_material_feeds.py']
    files=[]
    for name in allow:
        p=ROOT/name
        if not p.exists():raise FileNotFoundError('Required release source missing: '+name)
        files.append({'path':name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    # Release 0.3.0 packages engine.cjs at its own version (Compute.VERSION); the engine version is stamped into saved decisions and changes only with the arithmetic.
    manifest={'schema':'second-run/compute-release@1','version':'0.3.0','engineVersion':re.search(r"const VERSION='([^']+)'",(ROOT/'engine.cjs').read_text(encoding='utf-8')).group(1),'files':files}
    (ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    with zipfile.ZipFile(ROOT/'compute-kit.zip','w',compression=zipfile.ZIP_STORED) as z:
        for name in [x['path'] for x in files]+['MANIFEST.json']:
            info=zipfile.ZipInfo('compute/'+name,date_time=(2026,9,22,0,0,0));info.create_system=3;info.compress_type=zipfile.ZIP_STORED;info.external_attr=0o100644<<16;z.writestr(info,(ROOT/name).read_bytes())
    print(json.dumps({'page_sha256':hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),'zip_sha256':hashlib.sha256((ROOT/'compute-kit.zip').read_bytes()).hexdigest(),'files':len(files)},indent=2))
if __name__=='__main__':build()
