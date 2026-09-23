#!/usr/bin/env python3
"""Check source price tokens and preserve a diff receipt; never silently renew a price review.

This is a conservative drift detector, not an independently qualified pricing scraper.
A human approves changed catalog prices and effective dates after reading the source.
"""
import argparse,datetime,hashlib,json,re,sys,urllib.request,urllib.parse
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
class VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden:self.hidden-=1
    def handle_data(self,s):
        if not self.hidden:self.parts.append(s)
def plain(html):
    p=VisibleText();p.feed(html);return re.sub(r'\s+',' ',' '.join(p.parts))
def observe(text,offers):
    """Find price tokens near exact GPU names; ambiguous/missing matches require review."""
    rows=[]
    for o in offers:
        # A VM price can appear once above a table rather than next to every size.
        pattern=re.compile(re.escape(o['gpu']),re.I);segments=[text[max(0,m.start()-80):m.end()+230] for m in pattern.finditer(text)]
        amounts=sorted({float(v) for segment in segments for v in re.findall(r'\$\s*(\d+\.\d{2})(?!\d)',segment)})
        expected=sorted({o['rate'],*[s['rate'] for s in o['schedules']]})
        rows.append({'id':o['id'],'expected_rates':expected,'observed_nearby_currency_values':amounts,'state':'EXPECTED_TOKENS_PRESENT' if all(v in amounts for v in expected) else 'REVIEW_REQUIRED','semantic_price_verified':False})
    return rows
def review(c,htmls):
    observations=[]
    for p in c['providers']:
        source=c['sources'][p['source']];raw=htmls.get(p['id'])
        if raw is None:observations.append({'provider':p['id'],'url':source['url'],'state':'SOURCE_UNAVAILABLE','rows':[]});continue
        rows=observe(plain(raw),[o for o in c['offers'] if o['provider']==p['id']]);observations.append({'provider':p['id'],'url':source['url'],'source_sha256':hashlib.sha256(raw.encode()).hexdigest(),'state':'REVIEW_REQUIRED' if any(r['state']!='EXPECTED_TOKENS_PRESENT' for r in rows) else 'TOKENS_PRESENT_REVIEW_DATE_UNCHANGED','rows':rows})
    return {'schema':'second-run/price-review@1','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'catalog_sha256':hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),'catalog_reviewed_on':c['reviewedOn'],'state':'REVIEW_REQUIRED' if any(o['state'] in ('SOURCE_UNAVAILABLE','REVIEW_REQUIRED') for o in observations) else 'TOKENS_PRESENT_REVIEW_DATE_UNCHANGED','observations':observations,'price_date_renewed':False,'boundary':'Token presence is drift triage, not semantic quote validation. Source formats, billing scope and effective dates require approval.'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-dir',type=Path);p.add_argument('--fetch',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();c=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'));htmls={}
    if not a.source_dir and not a.fetch:p.error('Choose --source-dir (retained provider HTML) or --fetch (four public source requests).')
    for provider in c['providers']:
        try:
            if a.source_dir:htmls[provider['id']]=(a.source_dir/(provider['id']+'.html')).read_text(encoding='utf-8')
            else:
                url=c['sources'][provider['source']]['url'];req=urllib.request.Request(url,headers={'User-Agent':'Second-Run-Compute-Price-Review/0.1'})
                with urllib.request.urlopen(req,timeout=15) as r:
                    if urllib.parse.urlparse(r.url).hostname!=urllib.parse.urlparse(url).hostname:raise ValueError('Cross-host redirect held')
                    b=r.read(4*1024*1024+1)
                    if len(b)>4*1024*1024:raise ValueError('Source too large')
                    htmls[provider['id']]=b.decode('utf-8')
        except Exception:pass
    r=review(c,htmls);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'state':r['state'],'receipt':str(a.out),'review_date_unchanged':True}));return 2 if r['state']=='REVIEW_REQUIRED' else 0
if __name__=='__main__':sys.exit(main())
