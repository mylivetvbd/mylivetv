#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Robot v2 — SAFE nightly refresher:
#   NEVER modifies/removes existing lines; only APPENDS new, deep-checked
#   channels into EXISTING categories (cap 300). Grouping stays intact forever.
import re, ssl, sys, urllib.request, urllib.parse, concurrent.futures, random

MASTER = 'my-channels-master.m3u'
CAP = 300        # per-category max (user rule)
MAX_ADD = 120    # max new channels per night
MAX_CHECK = 600  # max deep live-checks per night
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = 'VLC/3.0.20 LibVLC/3.0.20'

def fetch_n(url, n, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return r.read(n)

master = open(MASTER, encoding='utf-8').read()
lines = master.splitlines()
entries = []
i = 0
while i < len(lines):
    if lines[i].startswith('#EXTINF'):
        ext = lines[i]; j = i + 1
        while j < len(lines) and lines[j].startswith('#'): j += 1
        if j < len(lines) and lines[j].strip(): entries.append((ext, lines[j].strip()))
        i = j + 1
    else: i += 1

def norm(x): return re.sub(r'[^a-z0-9\u0980-\u09ff]+', '', x.lower())
have_url = {u for _, u in entries}
have_name = {norm(e.rsplit(',', 1)[-1]) for e, _ in entries}
gcount = {}
for e, _ in entries:
    g = (re.search(r'group-title="([^"]*)"', e) or [None, ''])[1]
    gcount[g] = gcount.get(g, 0) + 1
def gfind(key):
    for g in gcount:
        if key in g: return g
    return None

src = fetch_n('https://iptv-org.github.io/iptv/index.category.m3u', 50_000_000, 60).decode('utf-8', 'ignore').splitlines()
cands = []
i = 0
while i < len(src):
    if src[i].startswith('#EXTINF'):
        ext = src[i]; j = i + 1
        while j < len(src) and src[j].startswith('#'): j += 1
        if j < len(src) and src[j].strip():
            u = src[j].strip()
            nm = ext.rsplit(',', 1)[-1].strip()
            if u not in have_url and norm(nm) not in have_name and u.startswith('http'):
                cat = (re.search(r'group-title="([^"]*)"', ext) or [None, ''])[1].lower()
                lg = (re.search(r'tvg-logo="([^"]*)"', ext) or [None, ''])[1]
                cands.append((nm, lg, u, cat))
        i = j + 1
    else: i += 1

HIN = ('hindi','bollywood','zee ','sony ','colors','&tv','utsav','shemaroo','b4u','dangal')
ISL = ('islam','quran','koran','makkah','madani','sunnah','iqra','huda','deen')
CHR = ('ewtn','christ','catholic','gospel','church','jesus','tbn','daystar','3ab','sbn','hillsong','loveworld')
HND = ('aastha','sanskar','bhakti','ishwar','vedic','darshan')
def target(nm, cat):
    n = nm.lower()
    if 'sport' in cat:
        if 'cricket' in n: return gfind('ক্রিকেট')
        if any(x in n for x in ('football','soccer','futbol','futebol')): return gfind('ফুটবল')
        if 'tennis' in n: return gfind('টেনিস')
        if any(x in n for x in ('fight','wwe','ufc','box')): return gfind('ফাইট')
        if any(x in n for x in ('race','racing','motor','speed')): return gfind('রেসিং')
        return gfind('স্পোর্টস মিক্স')
    if 'movie' in cat:
        if any(x in n for x in HIN): return gfind('হিন্দি মুভি')
        return gfind('মুভি (গ্লোবাল) 2')
    if 'news' in cat: return gfind('নিউজ (গ্লোবাল) 2')
    if 'kids' in cat: return gfind('কিডস (গ্লোবাল)')
    if 'music' in cat: return gfind('মিউজিক (গ্লোবাল) 2')
    if 'documentary' in cat: return gfind('ডকুমেন্টারি (গ্লোবাল)') or gfind('ডকুমেন্টারি (ইংলিশ)')
    if 'religio' in cat:
        if any(x in n for x in ISL): return gfind('ইসলামিক')
        if any(x in n for x in CHR): return gfind('খ্রিস্টান')
        if any(x in n for x in HND): return gfind('হিন্দু')
        return gfind('ধর্মীয় (গ্লোবাল) 2')
    return None

picked = []
for nm, lg, u, cat in cands:
    g = target(nm, cat)
    if g and gcount.get(g, 0) < CAP:
        picked.append((nm, lg, u, g))
random.shuffle(picked)
picked = picked[:MAX_CHECK]
print(f'candidates={len(cands)} classified={len(picked)}(checking)')

def alive(u):
    try:
        if '.m3u8' in u.split('?')[0]:
            man = fetch_n(u, 300000, 6).decode('utf-8', 'ignore')
            seg = next((l.strip() for l in man.splitlines() if l.strip() and not l.startswith('#')), None)
            if not seg: return False
            s = urllib.parse.urljoin(u, seg)
            if '.m3u8' in s.split('?')[0]:
                man2 = fetch_n(s, 300000, 6).decode('utf-8', 'ignore')
                seg2 = next((l.strip() for l in man2.splitlines() if l.strip() and not l.startswith('#')), None)
                if not seg2: return False
                s = urllib.parse.urljoin(s, seg2)
            return len(fetch_n(s, 60000, 8)) > 20000
        return len(fetch_n(u, 60000, 8)) > 20000
    except Exception:
        return False

adds = []
with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
    futs = {ex.submit(alive, u): (nm, lg, u, g) for nm, lg, u, g in picked}
    for f in concurrent.futures.as_completed(futs):
        if len(adds) >= MAX_ADD: break
        nm, lg, u, g = futs[f]
        try:
            if f.result() and gcount.get(g, 0) < CAP:
                gcount[g] = gcount.get(g, 0) + 1
                adds.append((nm, lg, u, g))
        except Exception: pass

print(f'alive-added={len(adds)}')
if adds:
    block = '\n'.join(f'#EXTINF:-1 tvg-logo="{lg}" group-title="{g}",{nm}\n{u}' for nm, lg, u, g in adds)
    open(MASTER, 'a', encoding='utf-8').write('\n' + block + '\n')
    for nm, lg, u, g in adds[:10]: print(' +', g, '|', nm)
print('DONE')
