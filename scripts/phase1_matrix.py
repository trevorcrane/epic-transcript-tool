#!/usr/bin/env python3
"""Manual Phase 1 release-gate matrix runner."""
from __future__ import annotations

import json, time, sys, re
from urllib import parse, request, error

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://localhost:8090'
CASES = [
  {'name':'regression','url':'https://youtu.be/v34Eg12mhDM?si=lqfq-8bhlxADDZdD','expect':'ok','min_segments':700,'min_words':5000},
  {'name':'control','url':'https://youtu.be/dQw4w9WgXcQ','expect':'ok','min_segments':20,'min_words':100},
  {'name':'manual_caption','url':'https://youtu.be/dQw4w9WgXcQ','expect':'ok','min_segments':20,'min_words':100},
  {'name':'automatic_caption','url':'https://youtu.be/v34Eg12mhDM','expect':'ok','min_segments':700,'min_words':5000},
  {'name':'non_english','url':'https://youtu.be/kJQP7kiw5Fk','expect':'ok','min_segments':20,'min_words':50},
  {'name':'shorts','url':'https://www.youtube.com/shorts/SXHMnicI6Pg','expect':'ok','min_segments':1,'min_words':1},
  {'name':'long_video','url':'https://youtu.be/aircAruvnKk','expect':'ok','min_segments':100,'min_words':1000},
  {'name':'private_unavailable','url':'https://www.youtube.com/watch?v=aaaaaaaaaaa','expect':'blocked'},
  {'name':'invalid_url','url':'https://not-a-real.example/video','expect':'helpful'},
]

PUBLIC_HEADERS = {
    # Cloudflare can reject Python's default urllib user agent with 1010.
    "User-Agent": "Mozilla/5.0 Hermes EPIC Transcript release checker",
    "Accept": "application/json,text/plain,*/*",
}

def post(url):
    body=parse.urlencode({'url':url}).encode()
    req=request.Request(BASE + '/api/transcribe-url', data=body, headers={**PUBLIC_HEADERS, 'Content-Type':'application/x-www-form-urlencoded'}, method='POST')
    try:
        with request.urlopen(req, timeout=240) as r:
            return r.status, r.read().decode('utf-8','replace')
    except error.HTTPError as e:
        return e.code, e.read().decode('utf-8','replace')
    except Exception as e:
        return 0, str(e)

def valid_record(rec, case):
    segs=rec.get('segments') or []
    inc=all(float(segs[i].get('start',-1)) <= float(segs[i+1].get('start',-1)) for i in range(len(segs)-1))
    return len(segs)>=case.get('min_segments',0) and (rec.get('word_count') or 0)>=case.get('min_words',0) and bool(segs and segs[0].get('text') and segs[-1].get('text')) and inc

results=[]
for c in CASES:
    t=time.monotonic(); status, text=post(c['url']); dur=round(time.monotonic()-t,3)
    row={'case':c['name'],'http_status':status,'duration':dur,'ok':False}
    try:
        data=json.loads(text)
        if 'record' in data:
            r=data['record']; segs=r.get('segments') or []
            row.update(title=r.get('title') or r.get('source'), method=r.get('method'), cache_hit=r.get('cache_hit'), segment_count=len(segs), word_count=r.get('word_count'), language=r.get('language'), first=(segs[0].get('text')[:80] if segs else ''), last=(segs[-1].get('text')[:80] if segs else ''))
            row['ok']= status==200 and valid_record(r,c)
        else:
            detail=str(data.get('detail') or data.get('error') or '')
            row.update(error=detail[:300], helpful='upload it here' in detail or 'upload' in detail.lower())
            row['ok']= c['expect'] in {'blocked','helpful'} and row['helpful'] and status in {400,422}
    except Exception as e:
        row.update(parse_error=str(e), body=text[:300])
    results.append(row)
print(json.dumps({'base_url':BASE,'results':results,'all_ok':all(r['ok'] for r in results)}, indent=2, ensure_ascii=False))
sys.exit(0 if all(r['ok'] for r in results) else 1)
