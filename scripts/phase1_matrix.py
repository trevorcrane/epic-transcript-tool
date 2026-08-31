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
  {'name':'non_english','url':'https://youtu.be/kv92eqcZVxs','expect':'ok','min_segments':2,'min_words':30},
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

def post(path, data, timeout=240):
    body=parse.urlencode(data).encode()
    req=request.Request(BASE + path, data=body, headers={**PUBLIC_HEADERS, 'Content-Type':'application/x-www-form-urlencoded'}, method='POST')
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8','replace')
    except error.HTTPError as e:
        return e.code, e.read().decode('utf-8','replace')
    except Exception as e:
        return 0, str(e)

def get_json(path, timeout=30):
    req=request.Request(BASE + path, headers=PUBLIC_HEADERS, method='GET')
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8','replace')
    except error.HTTPError as e:
        return e.code, e.read().decode('utf-8','replace')
    except Exception as e:
        return 0, str(e)

def transcribe_url(url):
    """Use the same async YouTube path as the public UI, sync for other URLs."""
    if 'youtube.com/' in url or 'youtu.be/' in url:
        status, text = post('/api/transcribe-url-job', {'url': url}, timeout=60)
        if status != 202:
            return status, text
        try:
            job_id = json.loads(text)['job']['id']
        except Exception:
            return status, text
        deadline = time.monotonic() + 900
        last_status, last_text = status, text
        while time.monotonic() < deadline:
            last_status, last_text = get_json(f'/api/jobs/{job_id}', timeout=30)
            try:
                payload = json.loads(last_text)
                job = payload.get('job') or {}
                if job.get('status') == 'done':
                    return 200, json.dumps({'ok': True, 'record': job.get('record')}, ensure_ascii=False)
                if job.get('status') == 'error':
                    return int(job.get('status_code') or 422), json.dumps({'detail': job.get('error') or 'Job failed'}, ensure_ascii=False)
            except Exception:
                pass
            time.sleep(2)
        return 0, f'job timed out; last_status={last_status} body={last_text[:300]}'
    return post('/api/transcribe-url', {'url': url}, timeout=240)

def valid_record(rec, case):
    segs=rec.get('segments') or []
    inc=all(float(segs[i].get('start',-1)) <= float(segs[i+1].get('start',-1)) for i in range(len(segs)-1))
    return len(segs)>=case.get('min_segments',0) and (rec.get('word_count') or 0)>=case.get('min_words',0) and bool(segs and segs[0].get('text') and segs[-1].get('text')) and inc

results=[]
for c in CASES:
    t=time.monotonic(); status, text=transcribe_url(c['url']); dur=round(time.monotonic()-t,3)
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
