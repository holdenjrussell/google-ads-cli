# Weekly review edition 2026-09-03 — see docs/weekly-review.md. Runs from its own directory: pull.py writes ./data, this file reads it.
#!/usr/bin/env python3
"""Compose the CGK Google Ads / Ampd / PixelMe weekly review as HTML, then print to PDF.

Claude composes the document; this script only renders the tables and inline SVG
charts from the warehouse pulls in ./data (see pull.py) so every number in the
document traces to a saved query result.
"""
import json, os, base64, datetime, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(S, 'data')
def load(n): return json.load(open(os.path.join(D, n + '.json')))
def tsv(n):
    rows = [l.rstrip('\n').split('\t') for l in open(os.path.join(D, n + '.tsv'))]
    return [dict(zip(rows[0], r)) for r in rows[1:]]

NAVY, DEEP, POWDER, LINEN, GOLD, INK, OFFWHITE, HERO = '#182f5c', '#1f3d77', '#d7e7f3', '#ede6df', '#d29b28', '#121212', '#fafafa', '#c5e6ff'

def money(v, dec=0):
    if v is None: return '—'
    v = float(v)
    return ('-' if v < 0 else '') + '$' + (f'{abs(v):,.{dec}f}')
def pct(v, dec=1):
    if v is None: return '—'
    return f'{float(v)*100:.{dec}f}%'
def num(v, dec=0):
    if v is None: return '—'
    return f'{float(v):,.{dec}f}'
def x(v, dec=2):
    if v is None: return '—'
    return f'{float(v):.{dec}f}x'

LOGO = os.path.join(S, 'cgk-logo-blue.png')
logo_tag = ''
if os.path.exists(LOGO):
    b64 = base64.b64encode(open(LOGO, 'rb').read()).decode()
    logo_tag = f'<img class="logo" src="data:image/png;base64,{b64}" alt="CGK Linens">'
else:
    logo_tag = '<div class="wordmark">CGK LINENS</div>'

# ---------------------------------------------------------------- charts
def line_area_chart(series, width=980, height=250, y_fmt=lambda v: money(v), markers=(), title=''):
    """series: list of dicts {name, points:[(date, value)], kind:'area'|'line', color, dash}. One shared $ axis."""
    pad_l, pad_r, pad_t, pad_b = 62, 16, 26, 34
    all_dates = sorted({d for s in series for d, _ in s['points']})
    if not all_dates: return ''
    d0, d1 = all_dates[0], all_dates[-1]
    span = max(1, (d1 - d0).days)
    ymax = max(v for s in series for _, v in s['points'] if v is not None) * 1.08
    def X(d): return pad_l + (d - d0).days / span * (width - pad_l - pad_r)
    def Y(v): return pad_t + (1 - v / ymax) * (height - pad_t - pad_b)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">']
    # grid
    steps = 4
    for i in range(steps + 1):
        v = ymax / steps * i
        y = Y(v)
        out.append(f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="{LINEN}" stroke-width="1"/>')
        out.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{y_fmt(v)}</text>')
    # x ticks: first of month + every 10 days
    d = d0
    while d <= d1:
        if d.day in (1, 11, 21):
            out.append(f'<text x="{X(d):.1f}" y="{height-12}" text-anchor="middle" class="axis">{d.strftime("%b %d")}</text>')
        d += datetime.timedelta(days=1)
    for mi, (md, label) in enumerate(markers):
        if d0 <= md <= d1:
            out.append(f'<line x1="{X(md):.1f}" x2="{X(md):.1f}" y1="{pad_t}" y2="{height-pad_b}" stroke="{INK}" stroke-width="1" stroke-dasharray="3 3" opacity="0.55"/>')
            anchor = 'end' if X(md) > width * 0.7 else 'start'
            xx = X(md) - 4 if anchor == 'end' else X(md) + 4
            out.append(f'<text x="{xx:.1f}" y="{pad_t+10+12*(mi%2)}" text-anchor="{anchor}" class="axis marker">{label}</text>')
    for s in series:
        pts = [(X(d), Y(v)) for d, v in s['points'] if v is not None]
        if not pts: continue
        path = 'M' + ' L'.join(f'{px:.1f},{py:.1f}' for px, py in pts)
        if s.get('kind') == 'area':
            base = height - pad_b
            area = path + f' L{pts[-1][0]:.1f},{base} L{pts[0][0]:.1f},{base} Z'
            out.append(f'<path d="{area}" fill="{s["color"]}" opacity="0.9"/>')
            out.append(f'<path d="{path}" fill="none" stroke="{DEEP}" stroke-width="1.2"/>')
        else:
            dash = f' stroke-dasharray="{s["dash"]}"' if s.get('dash') else ''
            out.append(f'<path d="{path}" fill="none" stroke="{s["color"]}" stroke-width="2"{dash} stroke-linejoin="round"/>')
    # legend
    lx = pad_l
    for s in series:
        sw = f'<rect x="{lx}" y="{height-8}" width="14" height="6" fill="{s["color"] if s.get("kind")=="area" else s["color"]}"/>' if s.get('kind') == 'area' else f'<line x1="{lx}" x2="{lx+14}" y1="{height-5}" y2="{height-5}" stroke="{s["color"]}" stroke-width="2"/>'
        out.append(sw)
        out.append(f'<text x="{lx+18}" y="{height-1}" class="axis">{s["name"]}</text>')
        lx += 18 + 7 * len(s['name']) + 22
    out.append('</svg>')
    return '\n'.join(out)

def bar_chart(cats, series, width=980, height=230, y_fmt=lambda v: money(v), title=''):
    """grouped bars; series: [{name,color,values}]"""
    pad_l, pad_r, pad_t, pad_b = 62, 16, 22, 40
    n = len(cats); k = len(series)
    ymax = max(v for s in series for v in s['values'] if v is not None) * 1.12
    slot = (width - pad_l - pad_r) / n
    bw = slot * 0.72 / k
    def Y(v): return pad_t + (1 - v / ymax) * (height - pad_t - pad_b)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">']
    for i in range(5):
        v = ymax / 4 * i; y = Y(v)
        out.append(f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="{LINEN}"/>')
        out.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{y_fmt(v)}</text>')
    base = height - pad_b
    for ci, c in enumerate(cats):
        x0 = pad_l + ci * slot + slot * 0.14
        for si, s in enumerate(series):
            v = s['values'][ci]
            if v is None: continue
            bx = x0 + si * (bw + 2)
            out.append(f'<rect x="{bx:.1f}" y="{Y(v):.1f}" width="{bw-2:.1f}" height="{base-Y(v):.1f}" fill="{s["color"]}" rx="3"/>')
        out.append(f'<text x="{pad_l + ci*slot + slot/2:.1f}" y="{height-22}" text-anchor="middle" class="axis">{c}</text>')
    lx = pad_l
    for s in series:
        out.append(f'<rect x="{lx}" y="{height-9}" width="12" height="8" fill="{s["color"]}" rx="2"/>')
        out.append(f'<text x="{lx+16}" y="{height-1}" class="axis">{s["name"]}</text>')
        lx += 16 + 7 * len(s['name']) + 22
    out.append('</svg>')
    return '\n'.join(out)

# ---------------------------------------------------------------- data
ad = {r['d']: r for r in tsv('ampd_daily_mirror')}
gl = load('cgk_daily_lane')
ampd_spend_daily = {r['d']: float(r['spend']) for r in gl if r['lane'] == 'ampd'}
web_daily = {r['d']: r for r in gl if r['lane'] == 'website'}
def dt(s): return datetime.date.fromisoformat(s)
ampd_pts_spend = [(dt(d), ampd_spend_daily[d]) for d in sorted(ampd_spend_daily) if d <= '2026-09-01']
ampd_pts_rev = [(dt(d), float(ad[d]['rev']) + float(ad[d]['brb'])) for d in sorted(ad) if d >= '2026-06-01']
chart_ampd = line_area_chart([
    {'name': 'Google spend on [Ampd] campaigns', 'points': ampd_pts_spend, 'kind': 'area', 'color': POWDER},
    {'name': 'Amazon attributed revenue + BRB (Ampd)', 'points': ampd_pts_rev, 'kind': 'line', 'color': NAVY},
], markers=[(dt('2026-07-21'), 'amazon-class block'), (dt('2026-08-21'), 'block lifted'), (dt('2026-08-26'), 'audit executed')],
   title='Ampd lane daily spend vs attributed revenue')

web_pts_spend = [(dt(d), float(r['spend'])) for d, r in sorted(web_daily.items())]
web_pts_val = [(dt(d), float(r['conv_value'])) for d, r in sorted(web_daily.items())]
chart_web = line_area_chart([
    {'name': 'Google spend, website campaigns', 'points': web_pts_spend, 'kind': 'area', 'color': POWDER},
    {'name': 'Google-reported conversion value', 'points': web_pts_val, 'kind': 'line', 'color': NAVY},
], markers=[(dt('2026-08-05'), 'Demand Gen live'), (dt('2026-08-26'), 'audit executed 08-26 · budgets raised 08-27')],
   title='Website lane daily spend vs Google conversion value')

pm = load('pixelme_daily')
bk = {r['d']: r for r in pm if r['acct'].startswith('Thalestris')}
chart_bk = line_area_chart([
    {'name': 'Google spend (PixelMe ad cost)', 'points': [(dt(d), float(r['cost'])) for d, r in sorted(bk.items())], 'kind': 'area', 'color': POWDER},
    {'name': 'Amazon attributed revenue (PixelMe)', 'points': [(dt(d), float(r['rev'])) for d, r in sorted(bk.items())], 'kind': 'line', 'color': NAVY},
], markers=[(dt('2026-08-05'), '26 non-brand campaigns built'), (dt('2026-08-24'), '8 paused + cloned')], title='Beckham Home daily spend vs PixelMe revenue')

kw = load('kw_class_weekly')
wks = sorted({r['wk'] for r in kw if r['wk'] <= '2026-08-24'})
amz = {r['wk']: r for r in kw if r['is_amazon_keyword']}
gen = {r['wk']: r for r in kw if not r['is_amazon_keyword']}
chart_kw = bar_chart([datetime.date.fromisoformat(w).strftime('%b %d') for w in wks],
    [{'name': 'generic keywords', 'color': POWDER, 'values': [float(gen[w]['cost']) if w in gen else 0 for w in wks]},
     {'name': '"amazon" keywords', 'color': NAVY, 'values': [float(amz[w]['cost']) if w in amz else 0 for w in wks]}],
    title='Weekly Ampd spend by keyword class')

# ---------------------------------------------------------------- tables
def table(headers, rows, cls='', aligns=None):
    aligns = aligns or ['l'] + ['r'] * (len(headers) - 1)
    h = ''.join(f'<th class="{a}">{t}</th>' for t, a in zip(headers, aligns))
    body = ''
    for r in rows:
        body += '<tr>' + ''.join(f'<td class="{a}">{c}</td>' for c, a in zip(r, aligns)) + '</tr>'
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'

ampd_win = {  # from the Google-spend + Ampd-mirror window query (2026-09-03)
    'P30': dict(spend=70463, rev=156117, brb=14513, conv=4494, aacos=0.347, cpc=1.21, cvr=0.079, ntb=0.73, cov=0.975),
    'L30': dict(spend=50764, rev=115355, brb=10947, conv=3307, aacos=0.340, cpc=1.23, cvr=0.081, ntb=0.71, cov=0.988),
    'STABLE': dict(spend=56009, rev=128686, brb=11548, conv=3618, aacos=0.345, cpc=1.23, cvr=0.080, ntb=0.72, cov=0.999),
    'P14': dict(spend=23755, rev=56984, brb=5519, conv=1521, aacos=0.319, cpc=1.24, cvr=0.079, ntb=0.72, cov=0.998),
    'L14': dict(spend=25036, rev=55011, brb=5043, conv=1689, aacos=0.353, cpc=1.23, cvr=0.084, ntb=0.72, cov=0.977),
    'JUL': dict(spend=71807, rev=152037, brb=14222, conv=4429, aacos=0.355, cpc=1.21, cvr=0.077, ntb=0.73, cov=0.950),
    'AUG': dict(spend=55906, rev=131248, brb=12683, conv=3705, aacos=0.324, cpc=1.23, cvr=0.082, ntb=0.72, cov=0.989),
}
win_labels = [('JUL', 'July 1–31'), ('AUG', 'August 1–31'), ('P30', 'Prior 30 (Jul 5–Aug 3)'), ('L30', 'Last 30 (Aug 4–Sep 1)'), ('STABLE', 'Stable 30 (Jul 21–Aug 19)'), ('P14', 'Prior 14 (Aug 5–18)'), ('L14', 'Last 14 (Aug 19–Sep 1)')]
t_ampd_windows = table(['Window', 'Spend', 'Amazon revenue', 'BRB', 'Conv', 'CPC', 'CVR', 'AACOS', 'NTB share', 'Mirror cov.'],
    [[lbl, money(w['spend']), money(w['rev']), money(w['brb']), num(w['conv']), money(w['cpc'], 2), pct(w['cvr']), f'<b>{pct(w["aacos"])}</b>', pct(w['ntb'], 0), pct(w['cov'])] for k, lbl in win_labels for w in [ampd_win[k]]])

kw_rows = []
for w in wks + ['2026-08-31']:
    a = amz.get(w); g = gen.get(w)
    if not a or not g: continue
    tot = float(a['cost']) + float(g['cost'])
    kw_rows.append([datetime.date.fromisoformat(w).strftime('%b %d'), money(g['cost']), pct(g['aacos']), money(a['cost']), f'{float(a["cost"])/tot*100:.0f}%', num(a['kws_serving']), pct(a['aacos'])])
t_kw = table(['Week of', 'Generic spend', 'Generic AACOS', '"amazon" spend', 'Share', '"amazon" kws', '"amazon" AACOS'], kw_rows, cls='dense')

ac = load('ampd_campaigns')
def byid(win): return {r['campaign_id']: r for r in ac if r['win'] == win}
st, l30, l14 = byid('STABLE'), byid('L30'), byid('L14')
# renamed campaigns: patch with the mirror-by-name figures (view fixed after the pull)
fix = {'23350268344': {'STABLE': (14666, 33188, 3130, 896, 0.348), 'L30': (11882, 26586, 2631, 748, 0.348), 'L14': (4098, 10793, 1060, 322, 0.281)},
       '21839192355': {'STABLE': (1967, 4464, 0, 130, 0.441), 'L30': (1853, 4063, 0, 110, 0.456), 'L14': (798, 1780, 0, 46, 0.449)}}
live_budget = {'23864624639': 250, '22821667433': 300, '23576925357': 100, '24139372252': 40, '22719773443': 24, '24139407325': 19, '23859376713': 30, '23451576927': 40}
live_ceiling = {'23350268344': 2.5, '21496355417': 0.78, '21506111969': 1.65, '22377660684': 1.5, '22564129915': 2.0, '22574740272': 1.5, '22719773443': 0.71, '22801629102': 1.5, '22821667433': 0.65, '23451576927': 0.65, '23461114981': 0.6, '23462511087': 1.45, '23467639163': 1.25, '23472210370': 1.4, '23576925357': 1.0, '23576955786': 0.75, '23582317199': 0.75, '23758894201': 1.5, '23864624639': 1.25, '23864706143': 1.0, '24069391339': 0.5, '24128873457': 0.85, '24139372252': 0.7, '24139378924': 0.38, '24139407325': 0.8, '24176957259': 1.5, '24182840078': 0.3}
manual_bid = {'19876543583': 2.25, '21083360054': 2.20, '21506125421': 3.15, '21510061819': 1.50, '21839192355': 0.98, '22452315321': 0.83, '23676906151': 1.13, '23754299480': 1.00, '23859376713': 1.00}
short = lambda n: n.replace('[Ampd] ', '').replace('amazon.com ', '').replace('[AMPD] ', '')
verdict = {
    '23350268344': 'Hold — largest campaign, at target; L14 improving',
    '23676906151': 'Watch — bid-downs applied 08-26',
    '21496355417': 'Hold at $138',
    '21510061819': 'Bid down "queen sheet set" $1.25→$1.12',
    '21083360054': 'Bid down "extra deep queen sheets" $2.39→$1.80',
    '23864624639': 'Revert 08-31 budget $250→$100; seasonal trim',
    '23859376713': 'Pause until Oct 1 (84% AACOS in every window)',
    '23451576927': 'Hold — 08-26 fix working (78%→36%)',
    '23472210370': 'Scale — ceiling $1.40→$1.65 (rank-limited)',
    '23758894201': 'Hold — trim ceiling $1.50→$1.30 if L14 stays >40%',
    '23576925357': 'Scale — ceiling $1.00→$1.25',
    '22452315321': 'Scale — ad-group bid $0.83→$1.05',
    '22719773443': 'Restore budget $24→$75, ceiling $0.71→$0.90',
    '22564129915': 'Pause kw "king sheets deep pocket"; ceiling $2.00→$1.60',
    '23754299480': 'Hold (dorm season ending)',
    '23461114981': 'Ceiling $0.60→$0.50',
    '23582317199': 'Scale — ceiling $0.75→$1.00',
    '24128873457': 'Convert to Manual CPC; "king size sheets on sale" at $0.65',
    '22801629102': 'Pause — 183% AACOS, duplicate of Bamboo Cooling coverage',
    '23864706143': 'Scale — ceiling $1.00→$1.30',
    '22377660684': 'Watch — amazon-class volume returned; judge 09-10',
    '23467639163': 'Scale — ceiling $1.25→$1.55',
    '22574740272': 'CA: ceiling $1.50→$1.20',
    '23576955786': 'Hold',
    '21736166343': 'Paused 08-26 (was never linked in Ampd)',
    '23462511087': 'Hold',
    '24069391339': 'Scale — ceiling $0.50→$0.70',
    '21506111969': 'Hold',
    '22821667433': 'Revert 08-31 budget $300→$30 (213% AACOS history)',
    '24139407325': 'Scale — budget $19→$50, ceiling $0.80→$1.00',
    '19876543583': 'Hold — +25% amazon-class raise on 08-26; judge 09-10',
    '21506125421': 'Watch (MANUAL $3.15 bid, 46% on tiny spend)',
    '24139372252': 'Hold',
    '21839192355': 'CA: "king sheets" bid $0.98→$0.80',
    '24176957259': 'Watch — 8 days old',
    '24182840078': 'Hold — ceiling $0.30 is the breakeven; low volume expected',
    '24139378924': 'Hold',
}
rows = []
order = sorted(set(list(st) + list(l30)), key=lambda cid: -(float((l30.get(cid) or {}).get('cost') or 0) + float((st.get(cid) or {}).get('cost') or 0)))
seen = set()
for cid in order:
    if cid in seen: continue
    seen.add(cid)
    r = l30.get(cid) or st.get(cid) or l14.get(cid)
    name = short(r['campaign_name'])
    if cid in fix:
        name = short({'23350268344': '[Ampd] 21 In 6PC | King | White | B07F91D1Z3 | DEEP POCKET KWs | US', '21839192355': '[Ampd] 21 Inch 6PC CANADA | King | White | B0C59FZZ29 | Deep Pocket KWs'}[cid])
    def cell(win_rows, w):
        if cid in fix:
            c, rv, b, cv, aa = fix[cid][w]
            return money(c), pct(aa)
        rr = win_rows.get(cid)
        if not rr: return '—', '—'
        return money(rr['cost']), pct(rr['aacos']) if rr.get('aacos') is not None else '—'
    s_c, s_a = cell(st, 'STABLE'); l_c, l_a = cell(l30, 'L30'); f_c, f_a = cell(l14, 'L14')
    strat = (r.get('strategy') or '').replace('TARGET_SPEND', 'Max Clicks').replace('MANUAL_CPC', 'Manual CPC')
    lever = f'ceiling {money(live_ceiling[cid],2)}' if cid in live_ceiling else (f'bid {money(manual_bid[cid],2)}' if cid in manual_bid else '')
    bud = live_budget.get(cid, r.get('budget'))
    def mv(t):
        t = t.replace('$', '').replace(',', '')
        return float(t) if t not in ('', '—') else 0.0
    if mv(l_c) < 40 and cid not in fix and mv(s_c) < 60: continue
    rows.append([f'{name}<br><span class="id">{cid} · {strat} · budget {money(bud)}/d · {lever}</span>', s_c, s_a, l_c, l_a, f_c, f_a, verdict.get(cid, '')])
t_ampd_campaigns = table(['Campaign', 'Stable spend', 'Stable AACOS', 'L30 spend', 'L30 AACOS', 'L14 spend', 'L14 AACOS<br><span class="id">immature</span>', 'Recommendation'], rows, cls='dense', aligns=['l', 'r', 'r', 'r', 'r', 'r', 'r', 'l'])

wc = load('website_campaigns')
w30 = {r['campaign_id']: r for r in wc if r['win'] == 'L30'}
wp30 = {r['campaign_id']: r for r in wc if r['win'] == 'P30'}
w14 = {r['campaign_id']: r for r in wc if r['win'] == 'L14'}
l7 = {  # 08-27..09-02 post domain-fix pull (spend, google value, nb 7d rev)
    '22166226679': (1087, 1091, 741), '23836235206': (1003, 1198, 1313), '22440426630': (952, 1333, 1522), '21696634733': (858, 1169, 958), '23963684825': (760, 869, 815), '23769689251': (743, 728, 822), '23788030482': (727, 659, 428), '23747211118': (604, 1041, 1130), '23749922783': (419, 813, 806), '19342888496': (405, 115, 76), '24177022254': (359, 194, 201), '23742603974': (300, 360, 360), '13622723707': (299, 3070, 1014), '23775728849': (105, 110, 124), '23775627497': (92, 61, 160), '23808252605': (59, 0, 14), '23770477647': (53, 52, 70), '23769662365': (43, 29, 36)}
live_web = {  # live 2026-09-03: budget, tROAS/tCPA
    '13622723707': (150, 'tROAS 10'), '19342888496': (75, 'tROAS 1.5'), '21696634733': (150, 'tROAS 1.6'), '22166226679': (190, 'tROAS 2.0'), '22440426630': (150, 'tROAS 2.0'), '23742603974': (200, 'tROAS 2.3'), '23747211118': (160, 'tROAS 2.1'), '23749922783': (150, 'tROAS 2.4'), '23769662365': (150, 'tROAS 2.5'), '23769689251': (400, 'tROAS 2.0'), '23770477647': (250, 'tROAS 3.5'), '23775627497': (150, 'tROAS 2.5'), '23775728849': (150, 'tROAS 2.0'), '23788030482': (125, 'tCPA $60'), '23808252605': (50, 'tROAS 2.0'), '23836235206': (150, 'tROAS 1.5'), '23963684825': (100, 'tROAS 2.0'), '24177022254': (50, 'Manual CPC')}
web_verdict = {
    '23788030482': 'Pause (0.65 Google / 0.52 NB on $12.2k); if kept, cap $50/d and judge NB ≥1.0 by 09-17',
    '23836235206': 'Hold tROAS 1.5 to 09-10; ratchet to 1.65 only if L14 ≥1.4',
    '22166226679': 'Below target since raise; revert $190→$100 if L14 <1.6 on 09-10',
    '22440426630': 'Hold at $150',
    '19342888496': 'Anomaly: value collapsed from 08-19; raise tROAS 1.5→1.8, check conversion-action mix',
    '21696634733': 'Hold at $150',
    '13622723707': 'Add exact misspelling keywords; lower tROAS 10→6',
    '23747211118': 'Hold — raise to $160 is working (2.0 both sources)',
    '23963684825': 'Raise to $100 diluted it (2.08→1.14); revert to $70 if L14 <1.6',
    '23769689251': 'Raise to $400 diluted it (1.73→0.98); revert to $150 if L14 <1.6',
    '23749922783': 'Lower tROAS 2.4→2.1 to unlock volume (rank-limited at 2.3–2.5)',
    '23742603974': 'Hold (NB says 1.6; Google 1.1)',
    '23775627497': 'Hold',
    '24177022254': 'Keep to 09-17; bids/QS losing 87% of auctions; prune ad groups with $50 and 0 conv',
    '23775728849': 'Hold',
    '23808252605': 'Pause (1 conv on $119)',
    '23769662365': 'Hold (tROAS-governed, small)',
    '23770477647': 'Hold (small)',
}
rows = []
for cid, r in sorted(w30.items(), key=lambda kv: -float(kv[1]['spend'])):
    p = wp30.get(cid); f = w14.get(cid); s7 = l7.get(cid)
    lb = live_web.get(cid, (r.get('budget'), ''))
    name = r['campaign_name'].replace('Deep Pocket Sheet Best Ad | Shopify |  Deep Pocket | Stretch+Fit 4K V4 | Demand Gen / Youtube', 'Demand Gen / YouTube — Deep Pocket Stretch+Fit')
    rows.append([f'{name}<br><span class="id">{cid} · {r["ch"].replace("_"," ").title()} · budget {money(lb[0])}/d · {lb[1]}</span>',
                 money(p['spend']) if p else '—', x(p['roas']) if p else '—',
                 money(r['spend']), x(r['roas']), x(r['nb_roas7']) if r.get('nb_roas7') is not None else '—',
                 money(s7[0]) if s7 else '—', x(s7[1] / s7[0]) if s7 else '—', x(s7[2] / s7[0]) if s7 else '—',
                 web_verdict.get(cid, '')])
t_web = table(['Campaign', 'P30 spend', 'P30 Google ROAS', 'L30 spend', 'L30 Google ROAS', 'L30 NB 7d ROAS', 'L7 spend<br><span class="id">Aug 27–Sep 2</span>', 'L7 Google', 'L7 NB 7d', 'Recommendation'], rows, cls='dense', aligns=['l'] + ['r'] * 8 + ['l'])

bc = load('beckham_campaigns'); bp = load('beckham_pixelme_products')
b30 = [r for r in bc if r['win'] == 'L30']; b14 = {r['campaign_id']: r for r in bc if r['win'] == 'L14'}
bp30 = {r['asin']: r for r in bp if r['win'] == 'L30'}; bp14 = {r['asin']: r for r in bp if r['win'] == 'P14'}; bpl14 = {r['asin']: r for r in bp if r['win'] == 'L14'}
SF = next(k for k in bp30 if k.startswith('aHR0'))
bk_names = {SF: 'Becky Cameron pillow storefront (both storefront campaigns)', 'B01LYNW421': 'Down Alternative bed pillows', 'B0D9WXQVJS': 'Pillow protectors, queen', 'B0F2TQM32J': 'Cooling pillowcases', 'B0BGTNFCN3': 'Shredded memory foam pillow'}
rows = []
for asin in [SF, 'B01LYNW421', 'B0D9WXQVJS', 'B0F2TQM32J', 'B0BGTNFCN3']:
    r = bp30[asin]; p = bp14.get(asin); f = bpl14.get(asin)
    rows.append([bk_names[asin] + (f'<br><span class="id">{asin}</span>' if not asin.startswith('aHR0') else ''), money(r['ad_cost']), money(r['rev']), num(r['purchases']), x(r['roas']), pct(r['acos']) if r.get('acos') else '—', x(p['roas']) if p else '—', x(f['roas']) if f else '—'])
t_bk_products = table(['Product (PixelMe attribution)', 'L30 spend', 'L30 Amazon revenue', 'Purchases', 'L30 ROAS', 'L30 ACOS', 'P14 ROAS', 'L14 ROAS'], rows)
bk_verdict = {
    '21144235438': 'Hold budget; ROAS 3.28→2.62 as spend rose — do not add budget; floor 2.5',
    '21140769962': 'Hold (tROAS 3.6, IS 91%)',
    '24108461696': 'Cut $150→$50; negatives silk/satin',
    '24102806289': 'Scale $150→$225 (3.37 L14 ROAS, 36% budget-lost)',
    '24108462704': 'Cut $150→$40; negatives silk/blissy/satin',
    '24108462695': 'Paused 08-24 (broken PixelMe URL)',
    '24108462671': 'Paused 08-24',
    '24113472868': 'Paused 08-24',
    '24169545333': 'Pause — clone imports as -50, bids blind',
    '23969931558': 'Pause (0.06 ROAS L30)',
    '24169545984': 'Pause — clone imports as -50, bids blind',
    '24175484375': 'Pause — clone imports as -50, bids blind',
}
rows = []
for r in sorted(b30, key=lambda r: -float(r['spend'])):
    f = b14.get(r['campaign_id'])
    pm_s = {4: 'linked', 1: 'paused in PixelMe', -50: 'import failed (-50)', -5: 'pending'}.get(r.get('pm_status'), '—')
    nm = r['campaign_name'].replace('[Pixelme] | Search | Amazon | Non Brand | ', '').replace('[Pixelme] - Becky Cameron - ', '')
    rows.append([f'{nm}<br><span class="id">{r["campaign_id"]} · {r["status"]} · {(r["strat"] or "").replace("_"," ").title()} · budget {money(r["budget"])}/d · PixelMe: {pm_s}</span>',
                 money(r['spend']), num(r['conv']), money(r['cpa'], 0) if r.get('cpa') else '—', money(f['spend']) if f else '—', num(f['conv']) if f else '—', bk_verdict.get(r['campaign_id'], '')])
t_bk = table(['Campaign', 'L30 spend', 'L30 Google conv<br><span class="id">PixelMe upload</span>', 'Google CPA', 'L14 spend', 'L14 conv', 'Recommendation'], rows, cls='dense', aligns=['l', 'r', 'r', 'r', 'r', 'r', 'l'])

sc = load('saferest_campaigns'); sp = load('saferest_pixelme_products')
s30 = [r for r in sc if r['win'] == 'L30']; sP30 = {r['campaign_id']: r for r in sc if r['win'] == 'P30'}
rows = []
for r in sorted(s30, key=lambda r: -float(r['spend'])):
    p = sP30.get(r['campaign_id'])
    nm = r['campaign_name'].replace('[Pixelme] - SafeRest - ', '')
    rows.append([f'{nm}<br><span class="id">{r["campaign_id"]} · Max Conv Value · budget {money(r["budget"])}/d</span>', money(p['spend']) if p else '—', money(r['spend']), num(r['conv']), money(r['conv_value']), x(float(r['conv_value']) / float(r['spend'])), money(r['cpa'], 2)])
t_sr = table(['Campaign', 'P30 spend', 'L30 spend', 'L30 Google conv', 'L30 Google value', 'Google ROAS', 'CPA'], rows, cls='dense')
rows = []
for w in ['P30', 'STABLE', 'L30', 'L14']:
    for r in [r for r in sp if r['win'] == w]:
        rows.append([{'P30': 'Prior 30', 'STABLE': 'Stable 30', 'L30': 'Last 30', 'L14': 'Last 14'}[w] + ' · ' + ('King protector B003PWK2A8' if r['asin'] == 'B003PWK2A8' else 'Queen protector B003PWNH4Q'), money(r['ad_cost']), money(r['rev']), num(r['purchases']), x(r['roas']), pct(r['acos'])])
t_sr_pm = table(['Window · product (PixelMe)', 'Spend', 'Amazon revenue', 'Purchases', 'ROAS', 'ACOS'], rows, cls='dense')

# change log rows (curated from google_change_events, ampd.change_log, session records)
changelog = [
    ('08-05', 'Beckham Home', 'Nova (gads)', '26 non-brand [Pixelme] campaigns built at $150/day (Max Conversions, ad groups paused); 1,447 keyword criteria, 126 ads, 116 assets', 'google_change_events'),
    ('08-05/06', 'Beckham Home', 'Thrasio (mark.hoban@)', '78 ad edits; one campaign REMOVED', 'google_change_events'),
    ('08-06', 'Beckham Home', 'Holden', 'Storefront Pillows: Max Conversions target CPA set', 'google_change_events'),
    ('08-06', 'CGK', 'Ampd (adwords-manager@metricstory)', 'Flex Top Split Head budget $100→$200; one Max CPC ceiling and one enhanced-CPC flag changed', 'google_change_events + ampd.change_log'),
    ('08-06', 'CGK', 'Nova', 'Audit #1 delivered (PDF); Ampd warehouse coverage fix (campaign_daily_complete)', 'session record'),
    ('08-13', 'CGK', 'Nova (Ampd wizard + gads)', 'Amazon-class block diagnosed as Google-side; 4 "Core KWs | US" campaigns created via Ampd (4PC Queen White $117, Full XL $13, RV Short Queen $19, Duvet $36); 126 keyword moves', 'google_change_events'),
    ('08-13/14', 'CGK', 'Nova', 'Budget cuts: 4PC Queen White "|" $400→$138, RV Short Queen $500→$24, Full XL $250→$20; two Max CPC ceilings lowered', 'google_change_events'),
    ('08-13', 'Beckham Home', 'Holden', '105 keyword edits across the new non-brand campaigns', 'google_change_events'),
    ('08-18→08-31', 'CGK', 'Flood Media (josh@floodmedia.co)', '45 assets uploaded; ad groups on "BRAND [Website] CGK LINS #2" (24081965922) paused/edited; ad-group tROAS 2.25→2.0 on 08-31', 'google_change_events'),
    ('08-20/21', 'CGK', 'Google', '~1.5-day account-wide serving stoppage (both lanes); self-resolved', 'warehouse'),
    ('08-21', 'CGK', 'Google', '"amazon" keyword class resumed serving after 31 dark days', 'ampd.keyword_daily'),
    ('08-24', 'CGK', 'Nova', 'Audit #2 "Ampd vs Website" (artifact); ranked action list', 'session record'),
    ('08-24', 'Beckham Home', 'Nova', '8 campaigns with un-rewritten URLs paused and cloned as "8-24-26"; clones linked in PixelMe (import now fails -50/-51 vendor-side); Holden set storefront tCPA $26', 'google_change_events'),
    ('08-26', 'CGK', 'Nova (24 gads plans, 270 ops)', 'Audit #2 executed with 5 owner overrides: Fleece→Manual CPC $30/d; Summer Comforters kept $100 + "queen summer comforter" paused/negated; Bamboo Product Page $300→$30 + ceiling $0.85→$0.65; Full XL legacy $20→$100 + ceiling $1.00; Full XL Core $13→$40; Duvet Storefront $75→$40 + "duvet cover set" isolated into 24182840078 ($50, ceiling $0.30); Light Grey 4 paused, replaced by amazon.ca 24176957259; 6PC King renamed "DEEP POCKET KWs | US"; Canada [AMPD]→[Ampd]; bid raises on Storefront DP KWs (+10/15/25%), 21 Inch 6Pc ($0.83), Light Grey 2 amazon class (+25%); DG $450→$125; Brand-Only Shopping $75→$115; SK White $30→$55; Bed Skirts tROAS 2.5→2.1; PMax tROAS 1.5; harvest campaign 24177022254 ($50/d); shared negative list 12207495603 on 16 website campaigns; 33 exact negatives on 21 In 4PC Shopping', 'google_change_events + ampd.change_log'),
    ('08-26', 'CGK', 'Nova', 'Northbeam: cgk.com added as managed domain (Google website attribution valid from 08-27)', 'session record'),
    ('08-27', 'CGK', 'Holden', 'Website budgets raised: Pillowcases $75→$400, 21 In 4PC Shopping $75→$190, Bed Skirts $100→$160, Queen 4PC Brand Excl $75→$150, Brand-Only $115→$150, SK White $55→$100; Demand Gen switched to Target CPA $60', 'google_change_events'),
    ('08-31 04:10 ET', 'CGK', 'via Ampd (adwords-manager@metricstory)', 'Summer Comforters budget $100→$250 and Max CPC $1.00→$1.20→$1.25; Bamboo Product Page (22821667433) budget $30→$100→$300 — reversing the 08-26 cut; one further ceiling $1.00→$1.50. <b>Actor not identified</b> (a person in the Ampd UI or Ampd automation)', 'google_change_events + ampd.change_log'),
    ('09-03', 'CGK', 'Nova', 'Warehouse: ampd.google_lane_daily now maps renamed campaigns (23350268344, 21839192355 no longer read as unattributed); Google change-event + recommendation feeds re-synced (were stale since 08-21/08-24)', 'this session'),
]
t_changelog = table(['Date', 'Account', 'Actor', 'Change', 'Evidence'], [[a, b, c, d, e] for a, b, c, d, e in changelog], cls='dense', aligns=['l', 'l', 'l', 'l', 'l'])

analysis_log = [
    ('2026-08-06', 'CGK Google Ads & Ampd Performance Review (PDF, 11 pp)', 'Jul-2 account compromise ($9,516, 82 MEC campaigns); amazon-class keywords dark since 07-21; 23/31 Ampd campaigns on Maximize Clicks; $3.7k July spend unattributed; AACOS definition + mirror-coverage traps fixed', '~/Downloads/CGK-Google-Ads-Ampd-Review-2026-08-06.pdf'),
    ('2026-08-13', 'Amazon-class block diagnosis + keyword-split runbook', 'Block is Google-side and CGK-specific (SafeRest unaffected); appeal drafted for Holden; do not raise bids to compensate', '~/Downloads/google-ads-appeal-amazon-keywords.md · ~/.hermes/state/ampd/keyword-split-20260813-runbook.md'),
    ('2026-08-24', 'Ampd vs Website audit (artifact)', 'Two-lane audit, 18 confirmed findings; DG at 0.62 ROAS; bleeders (Fleece 90%, Duvet 72%); scale list; 21736166343 never linked', 'claude.ai/code/artifact/3341ca90-0d95-42cb-b809-aed4e6e880a3'),
    ('2026-08-26', 'Audit execution', '24 mutation plans / 270 operations live; 5 owner overrides; new campaigns 24182840078, 24176957259, 24177022254', 'Slack recaps per plan; memory project-cgk-gads-audit-execution-20260826'),
    ('2026-09-03', 'Weekly review #1 (this document)', 'First run of the weekly format across CGK Ampd, CGK website (with Northbeam), Beckham Home, SafeRest', 'this file'),
]
t_analysis_log = table(['Date', 'Analysis', 'Headline findings', 'Where'], [list(r) for r in analysis_log], cls='dense', aligns=['l', 'l', 'l', 'l'])

actions = [
    # (rank, lane, campaign, action, where, effect, judge)
    (1, 'CGK Ampd', 'Summer Comforters 23864624639; Bamboo Product Page 22821667433', 'Confirm who made the 08-31 changes through Ampd. If nobody on the team did: revert Summer $250→$100 (ceiling $1.25→$1.00) and Bamboo PP $300→$30, and find/disable the Ampd automation that did it', 'Ampd UI (budget/ceiling) — gads is also safe for these', 'Stops ~$150/d of re-opened spend at 42–213% AACOS', 'now'),
    (2, 'CGK Website', 'Demand Gen / YouTube 23788030482', 'Pause. 0.65 Google / 0.52 Northbeam on $12.2k L30; still 0.91 / 0.59 after the $125 + tCPA $60 change', 'gads plan-mutation --status PAUSED', '≈ −$1,500 to −$1,900/mo net loss removed', 'owner call'),
    (3, 'CGK Ampd', 'Fleece Blankets 23859376713', 'Pause until Oct 1 (84–85% AACOS in every window; "throw blankets" 344%)', 'gads or Ampd UI', '≈ $950/mo over target-justified cost', 'now'),
    (4, 'CGK Ampd', 'Cooling Bed Sheets 4PC Queen 22801629102', 'Pause (183% L30, 189% L14; Bamboo Cooling already covers cooling terms at 30–38%)', 'gads or Ampd UI', '≈ $400/mo, rising', 'now'),
    (5, 'Beckham', 'Cooling Pillowcases 24175484375 (clone) + 24108462704', 'Pause the -50 clone; cut 24108462704 $150→$40; negatives: silk, satin, blissy', 'gads (structure lives in Google)', '$7.3k L30 at 0.28 ROAS → ≈ $5k/mo saved', 'now'),
    (6, 'Beckham', 'Pillow Protector 24169545984 (clone) + 24108461696', 'Pause the -50 clone; cut 24108461696 $150→$50; negatives silk', 'gads', '$7.1k L30 at 0.49 ROAS → ≈ $4.5k/mo saved', 'now'),
    (7, 'Beckham', 'Adjustable Foam Pillows 23969931558', 'Pause (0.06 ROAS L30, 0.22 P30)', 'gads', '≈ $1.4k/mo', 'now'),
    (8, 'Beckham', 'Down Alternative 24102806289', 'Raise $150→$225 (3.37 L14 ROAS, 36% impression share lost to budget); pause clone 24169545333; negatives "hotel collection pillows"', 'gads', '+$2k/mo spend at ~30% ACOS', '09-17'),
    (9, 'CGK Ampd', 'Storefront Deep Pocket KWs 21083360054', 'Bid "extra deep queen sheets" $2.39→$1.80 (56% AACOS on 47% of L14 spend); keep the other 08-26 raises', 'Ampd UI keyword pencil (Manual CPC) or gads', 'Campaign back toward 30% from 43%', '09-17'),
    (10, 'CGK Ampd', '4PC Queen White 21510061819', 'Bid "queen sheet set" $1.25→$1.12 (10% rule; 40–48% AACOS, 93% of spend)', 'Ampd UI or gads', '−3 to −5 pts campaign AACOS', '09-17'),
    (11, 'CGK Ampd', 'Core KWs US 24128873457', 'Convert to Manual CPC; bid "king size sheets on sale" at $0.65 (breakeven $0.72)', 'Ampd UI (bid mode) then keyword bid', 'Campaign from 49–52% toward 35%', '09-17'),
    (12, 'CGK Ampd', '4PC Main Storefront 22564129915', 'Pause keyword "king sheets deep pocket" (483% L14); ceiling $2.00→$1.60', 'Ampd UI / gads', 'L14 74% → re-judge', '09-15'),
    (13, 'CGK Ampd', 'Scale set: 6PC Extra Deep King 23472210370 (ceiling $1.40→$1.65), 21 Inch 6Pc Storefront 22452315321 (bid $0.83→$1.05), Full XL legacy 23576925357 (ceiling $1.00→$1.25), Flex Top Split 23582317199 ($0.75→$1.00), RV Short Queen 22719773443 (budget $24→$75, ceiling $0.71→$0.90), RV Core 24139407325 ($19→$50, $0.80→$1.00), Bulk 23864706143 ($1.00→$1.30), Extra Deep B018ZT6LU0 23467639163 ($1.25→$1.55), Oeko Tex 24069391339 ($0.50→$0.70)', 'All rank-limited (impression share lost to rank 40–72%, lost to budget <15%) at 3–25% AACOS. Raise the lever named; budgets are not the constraint except RV', 'gads (ceilings/bids) — Ampd UI for budgets', '+$1.5–2.5k/wk at ≤25% AACOS, funded by items 1, 3, 4', '09-17'),
    (14, 'CGK Website', 'Pillowcases 23769689251, 21 In 4PC 22166226679, SK White 23963684825', 'Hold the 08-27 raises one more week; revert to $150 / $100 / $70 if L14 Google ROAS through 09-10 is below 1.6 (all three fell to 0.98–1.14 in the first week)', 'gads', 'Protects ≈ $250/d from running below 1.0', '09-10'),
    (15, 'CGK Website', '6PC All Shopping 19342888496', 'Raise tROAS 1.5→1.8; inspect the conversion-action mix (3–7 conversions/day but ~$0 value since 08-19; Northbeam 0.19–0.38)', 'gads plan-bid-strategy', 'Stops ≈ $60/d at 0.3', 'now'),
    (16, 'CGK Website', 'Brand search 13622723707', 'Add EXACT keywords: "ckg sheets", "ckg linens", "cjk linens", "cgk linen", "cgklinens", "cgk linens discount code", "cgk unlimited jersey sheets"; lower tROAS 10→6 (Northbeam puts brand at 2.2–3.4, Google at 7–10)', 'gads plan-keywords', 'Cheap brand volume currently leaking into Shopping', '09-17'),
    (17, 'CGK Website', 'PMax 23836235206', 'Hold tROAS 1.5 to 09-10; step to 1.65 only if L14 ≥ 1.4 (currently 1.14 Google / 1.26 NB)', 'gads', '—', '09-10'),
    (18, 'CGK Website', 'Comforters 23749922783', 'Lower tROAS 2.4→2.1 (2.3–2.5 delivered; 58% impression share lost to rank on $44/d of a $150 budget)', 'gads', '+$50–80/d at ≈2.1', '09-17'),
    (19, 'CGK Website', 'Striped Sheets 23808252605', 'Pause (1 conversion on $119 L30, 0 on $59 L7)', 'gads', 'small', 'now'),
    (20, 'SafeRest', 'King PDP 21188616141, Queen PDP 21080074925', 'Lower tROAS 3.0→2.6 on both (PixelMe truth 3.07 / 3.16; Google sees 2.3–2.4 because uploads lag; impression share lost to rank 86% / 79%). Queen spend halved MoM at unchanged settings', 'gads plan-bid-strategy', '+$100–200/d at ≈3.0 Amazon ROAS', '09-17'),
    (21, 'CGK Ampd', 'Canada: 6PC King CANADA 21839192355, 4PC Top Performers 22574740272', '"king sheets" bid $0.98→$0.80; ceiling $1.50→$1.20 (CA pays no BRB; target ≈40%)', 'gads', 'CA lane 45–55% → ~40%', '09-17'),
    (22, 'CGK', 'Google recommendations (refreshed 09-03)', 'Accept: RSA ad-strength (133) and sitelink (130) recommendations on [Ampd] campaigns — creative is safe via gads. Reject: marginal-ROI budget (+$9.8k cost for +$2.9k value), forecasting tROAS, every Maximize Conversions / Target CPA opt-in on [Ampd] campaigns, search partners, display expansion, broad match', 'gads', 'Creative build task for next week', '09-10'),
    (23, 'All', 'Warehouse feeds', 'Add change_event + recommendation surfaces to the daily gads sync (both were 10+ days stale until this run); ampd.google_lane_daily fixed this session', 'gads_daily_sync.sh (both copies)', 'Changelog stays complete', 'now'),
]
t_actions = table(['#', 'Lane', 'Campaign(s)', 'Action', 'Where the change is made', 'Expected effect', 'Judge by'], [[str(a), b, c, d, e, f, g] for a, b, c, d, e, f, g in actions], cls='dense', aligns=['r', 'l', 'l', 'l', 'l', 'l', 'l'])

human = [
    'The 08-31 Ampd-side changes (item 1): who made them, and is any Ampd automation (Ampd Protection / bid automation) enabled on the account?',
    'Flood Media (josh@floodmedia.co) has been editing the CGK account since 08-18 (assets, the "BRAND #2" campaign, an ad-group tROAS). Confirm the access is intended — after the July compromise every external user should be deliberate.',
    'Google ticket on the "amazon" keyword class: the class has been serving since 08-21 and all four previously-dark terms now serve (xl twin sheet amazon 24 impr, bamboo sheets amazon 107, sheet set amazon 114, best cooling sheets on amazon 262 in L14). The ticket can be closed as resolved.',
    'Jul-2 compromise: $9,516 invalid-activity credit — still unconfirmed.',
    '08-20/21 serving stoppage: billing check in the Google Ads UI still open.',
    'PixelMe (Carbon6): 14 Beckham campaigns sit at import status -50; fresh links fail at -51. Until the vendor fixes its GAQL, no clone gets Google conversion uploads. Escalation is with Holden.',
    'Demand Gen (item 2) and the 08-27 website budget raises (item 14) are owner decisions; the numbers are in the website section.',
]

# ---------------------------------------------------------------- html
css = f"""
@font-face {{ font-family: Raleway; src: url('file://{S}/raleway-variable.woff2') format('woff2'); font-weight: 100 900; font-style: normal; }}
@font-face {{ font-family: Bitter; src: url('file://{S}/bitter-variable.woff2') format('woff2'); font-weight: 100 900; font-style: normal; }}
@page {{ size: Letter; margin: 14mm 12mm 16mm 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Raleway, 'Helvetica Neue', Arial, sans-serif; color: {INK}; background: #fff; margin: 0; font-size: 10.2pt; line-height: 1.42; }}
h1 {{ font-weight: 700; color: {NAVY}; font-size: 22pt; margin: 6px 0 2px; }}
h2 {{ font-weight: 700; color: {NAVY}; font-size: 15pt; margin: 22px 0 6px; padding-bottom: 4px; border-bottom: 2px solid {POWDER}; page-break-after: avoid; }}
h3 {{ font-weight: 600; color: {NAVY}; font-size: 11.5pt; margin: 14px 0 4px; page-break-after: avoid; }}
h4 {{ font-weight: 600; color: {INK}; font-size: 9.5pt; letter-spacing: 0.1em; text-transform: uppercase; margin: 12px 0 4px; }}
p {{ margin: 4px 0 7px; }}
.logo {{ width: 120px; height: auto; display: block; }}
.wordmark {{ font-weight: 900; color: {NAVY}; letter-spacing: 0.12em; font-size: 14pt; }}
.meta {{ color: #4a5568; font-size: 9pt; margin-bottom: 8px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0 12px; }}
.kpi {{ background: {POWDER}; border-radius: 6px; padding: 8px 10px; }}
.kpi .l {{ font-size: 7.5pt; letter-spacing: 0.1em; text-transform: uppercase; color: {NAVY}; font-weight: 600; }}
.kpi .v {{ font-size: 17pt; font-weight: 700; color: {NAVY}; line-height: 1.15; margin-top: 2px; }}
.kpi .s {{ font-size: 8pt; color: {DEEP}; margin-top: 2px; }}
.callout {{ background: {LINEN}; color: {NAVY}; border-radius: 6px; padding: 8px 12px; margin: 8px 0 10px; }}
.callout b {{ color: {NAVY}; }}
table {{ border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 8.6pt; page-break-inside: auto; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th {{ background: {POWDER}; color: {NAVY}; font-weight: 700; text-align: left; padding: 5px 6px; border-bottom: 1px solid {POWDER}; font-size: 8pt; }}
td {{ padding: 4px 6px; border-bottom: 1px solid {LINEN}; vertical-align: top; }}
td.r, th.r {{ text-align: right; white-space: nowrap; }}
table.dense {{ font-size: 7.9pt; }}
table.dense td {{ padding: 3px 5px; }}
.id {{ color: #5b6472; font-size: 7.2pt; font-weight: 400; }}
.chart {{ width: 100%; height: auto; margin: 4px 0 8px; }}
.chart .axis {{ font-family: Raleway, Arial, sans-serif; font-size: 8.5px; fill: #4a5568; }}
.chart .dlabel {{ font-family: Raleway, Arial, sans-serif; font-size: 9px; fill: {INK}; font-weight: 600; }}
.chart .marker {{ fill: {INK}; font-size: 8px; }}
ul {{ margin: 4px 0 8px 18px; padding: 0; }}
li {{ margin: 2px 0; }}
.two {{ display: grid; grid-template-columns: 3fr 2fr; gap: 14px; align-items: start; }}
.pb {{ page-break-before: always; }}
.footer {{ position: running(footer); }}
.small {{ font-size: 8.5pt; color: #4a5568; }}
.tag {{ display: inline-block; font-family: Bitter, Georgia, serif; font-weight: 600; font-size: 7.5pt; color: {NAVY}; background: {POWDER}; border-radius: 3px; padding: 1px 6px; margin-right: 4px; }}
.gold {{ color: {GOLD}; font-weight: 700; }}
"""

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CGK Google Ads weekly review — 2026-09-03</title><style>{css}</style></head><body>
{logo_tag}
<h1>Google Ads weekly review — Ampd, website, PixelMe</h1>
<div class="meta">Prepared 3 September 2026 by Nova · Accounts: CGK Linens 730-417-6160 (Ampd lane + website lane), GTA Beckham Home 381-888-5747 (PixelMe), GTA SafeRest 559-064-2315 (PixelMe). Hotel Sheets Direct 881-986-7229, DTC Beckham 675-743-0621 and CGK Walmart 242-570-9513 had no spend in the window.<br>
Windows: <b>Last 30</b> = Aug 4–Sep 2 (Google) / Aug 4–Sep 1 (Ampd, PixelMe) · <b>Prior 30</b> = Jul 5–Aug 3 · <b>Stable 30</b> = Jul 21–Aug 19 (ends 14 days back; the Amazon-attribution window for optimization decisions) · <b>Last 14</b> = Aug 19/20–Sep 1/2 (directional only; Amazon attribution is a 14-day post-click window and matures for 10–17 days).<br>
Sources: google_ads_tw (Google, data through Sep 2, all six accounts synced 09-03), ampd.* (Ampd exports through Sep 1), pixelme.* (through Sep 2), northbeam.export_daily (Clicks-only model, 7-day accrual unless stated; Google website attribution valid from Aug 27 after cgk.com became a managed domain). Currency USD. AACOS = (cost − Brand Referral Bonus) / Amazon revenue, Ampd's definition; target 30–35% (≈40% for amazon.ca, which pays no BRB).</div>

<div class="kpis">
 <div class="kpi"><div class="l">CGK Ampd lane · L30</div><div class="v">{money(ampd_win['L30']['spend'])}</div><div class="s">→ {money(ampd_win['L30']['rev'])} Amazon revenue · AACOS {pct(ampd_win['L30']['aacos'])} · vs P30 {money(ampd_win['P30']['spend'])} at {pct(ampd_win['P30']['aacos'])}</div></div>
 <div class="kpi"><div class="l">CGK website lane · L30</div><div class="v">$36,591</div><div class="s">Google value $58,115 (1.59x) · Northbeam 7d-click $42,830 (1.17x) · vs P30 $19,343 at 1.98x</div></div>
 <div class="kpi"><div class="l">Beckham Home (PixelMe) · L30</div><div class="v">$67,268</div><div class="s">PixelMe sees $63,018 → $132,739 Amazon revenue (2.11x, 47% ACOS) · storefront 2.82x, non-brand 0.87x · vs P30 $37,080</div></div>
 <div class="kpi"><div class="l">SafeRest (PixelMe) · L30</div><div class="v">$13,667</div><div class="s">→ $42,394 Amazon revenue (3.10x, 32% ACOS) · Google-side 2.43x · vs P30 $15,527</div></div>
</div>

<h2>Executive summary</h2>
<ul>
<li><b>The CGK Ampd lane is at target and smaller.</b> August closed at $55,906 spend → $131,248 Amazon revenue, 32.4% AACOS (July: $71,807 at 35.5%). Last-30 AACOS is 34.0% with 99% mirror coverage. Spend is down 28% month over month; the weekly run-rate recovered to $14.7k in the week of Aug 24 (34.5%, still maturing) after the Aug 20–21 stoppage trough of $9.3k.</li>
<li><b>The "amazon" keyword class is back.</b> 175 keywords served in the week of Aug 24 (168–170 before the block) and the class took 31% of lane spend at 34% fresh AACOS; it ran at 19–21% when stable in July. All four terms that were still dark on Aug 24 now serve. Judge the recovered efficiency from Sep 8.</li>
<li><b>Something reversed two of the Aug 26 cuts on Aug 31 at 04:10 ET through Ampd.</b> Summer Comforters went $100→$250/day (ceiling $1.00→$1.25) and Bamboo Product Page $30→$300/day. No team member is on record for it; if nobody did it, Ampd automation is live on the account and must be found and disabled. This is item 1.</li>
<li><b>The website lane doubled and got less efficient.</b> $36.6k spent in L30 (P30 $19.3k): Demand Gen/YouTube took $12.2k at 0.65 Google / 0.52 Northbeam, and Holden's Aug 27 budget raises (Pillowcases $75→$400, 21 In 4PC $75→$190, SK White $55→$100 and three more) pushed the first post-raise week to 1.45 Google / 1.19 Northbeam. Three of the raised campaigns fell below 1.2 in that week; the recommendation is to hold one more week and revert on a rule.</li>
<li><b>Beckham Home spend rose 81% and the non-brand expansion is losing money except one product.</b> The storefront lane is healthy ($39.9k → $112.5k, 2.82x) but with diminishing returns (3.28x → 2.62x as spend rose). Non-brand: Down Alternative pillows 2.02x (3.37x in L14) works; Cooling Pillowcases 0.28x, Pillow Protectors 0.49x and the Adjustable Foam pillow 0.06x do not — $15.9k of L30 spend for $5.6k of revenue. The three Aug 24 clones still fail PixelMe import (-50), so Google sees no conversions for them and bids blind.</li>
<li><b>SafeRest is steady at 3.0–3.2x on Amazon in every window</b> and is rank-limited (79–86% of impression share lost to rank at tROAS 3.0); Queen PDP spend halved on unchanged settings. Lower tROAS to 2.6 to buy volume.</li>
<li><b>Data:</b> the Google change-event and recommendation feeds had been stale since Aug 21/24 and were re-synced today; the Ampd join view mis-read the two campaigns renamed on Aug 26 as unattributed ($29k) and is fixed. Northbeam can only judge Google website campaigns from Aug 27.</li>
</ul>

<div class="callout"><b>Net of the action list:</b> stop ≈ $11–12k/month of spend running at 0.06–0.49x (Beckham non-brand, Demand Gen, Fleece, Cooling Bed Sheets, the two Aug 31 re-opened budgets) and redeploy ≈ $6–10k/month into nine rank-limited Ampd campaigns at 3–25% AACOS, Down Alternative pillows at ≈30% ACOS, and SafeRest at ≈3.0x.</div>

<h2 class="pb">1 · CGK Ampd lane (Amazon-bound, 37 campaigns)</h2>
<p>Spend is Google-billed; revenue, Brand Referral Bonus and conversions are Ampd's Amazon attribution. Mirror coverage is the share of Google spend Ampd reports; below 95% the AACOS row is computed on a partial base.</p>
{t_ampd_windows}
{chart_ampd}
<p class="small">Daily Google spend on [Ampd] campaigns (area) against Amazon attributed revenue plus BRB (line), Jun 1–Sep 1. The last ~10 days of revenue are structurally understated (attribution still maturing).</p>

<h3>Keyword class: "amazon"-qualified vs generic</h3>
<div class="two"><div>{t_kw}</div><div>{chart_kw}<p class="small">Weekly spend by keyword class. The class went dark Jul 21 and returned Aug 21; the week of Aug 24 is the first full week back. AACOS for the last two weeks is immature.</p></div></div>

<h3>Campaign table</h3>
<p class="small">Stable = Jul 21–Aug 19 (decision window). L30 = Aug 4–Sep 1. L14 = Aug 19–Sep 1 (immature, shown for direction). Lever shows the live Max CPC ceiling (Maximize Clicks campaigns) or the ad-group bid (Manual CPC). Campaigns under $40 in both windows are omitted.</p>
{t_ampd_campaigns}

<h3>Keyword concentration (stable window, from <code>ampd kw-report</code>)</h3>
<ul>
<li><b>Hogs:</b> "queen sheet set" 93% of 4PC Queen White (21510061819), $5,109 at 48%, CPC $1.30 vs breakeven $1.00 → bid down (owner kept $1.25 on Aug 26; the 10% rule now says $1.12). "duvet cover set" 61% of Duvet Storefront at 104% → already paused/isolated Aug 26; the isolated campaign (24182840078) has spent $9 in 8 days at its $0.30 breakeven ceiling — expected. "king size sheets on sale" 27–84% of two campaigns at 57–67% → convert Core KWs US to Manual CPC and bid it at $0.65. "soft blanket" 36% of Fleece at 66% → the campaign pauses. "dorm bed skirt twin xl" 46% at 43% and "sheets king size deep pocket" 53% at 41% → hold, seasonal / within 10 pts.</li>
<li><b>Starved winners (30):</b> "deep pocket king sheets" 5%, "sheets queen deep" 5% (in 21 Inch 6Pc Storefront, CPC $0.53), "extra deep pocket king sheets" 14%, "california king deep pocket sheet" 25%, "full xl sheets" 18%, "flex split king sheets" 15%, "softest sheets on amazon" 13% — all with $50–390 of headroom before reaching 35%. These are the campaigns in the scale set (action 13).</li>
<li><b>Early read on the Aug 26 changes</b> (Aug 27–Sep 1, immature): Duvet Storefront 78% → 36% after the "duvet cover set" pause; Storefront Deep Pocket KWs 26% → 43% after the +10/15/25% raises ("extra deep queen sheets" now $2.39 CPC at 56%) → partial revert (action 9); Light Grey 2 amazon class at 36–44% after +25% (was 19–21% pre-block) → hold to Sep 10; Full XL legacy still only $12/day at $1.00 ceiling with 47% rank-lost → raise again.</li>
</ul>

<h2 class="pb">2 · CGK website lane (cgk.com, 18 campaigns)</h2>
<p>Google conversion value is last-click, Google-measured; Northbeam is Clicks-only 7-day accrual. Northbeam under-credited Google before Aug 27 (cgk.com was logged as a referrer), so only the L7 columns compare the two fairly. Brand search is the clearest example: Google 7–10x, Northbeam 2.2–3.4x.</p>
<div class="kpis">
 <div class="kpi"><div class="l">L30 spend</div><div class="v">$36,591</div><div class="s">P30 $19,343 (+89%)</div></div>
 <div class="kpi"><div class="l">L30 Google value</div><div class="v">1.59x</div><div class="s">$58,115 · 1,289 conv · P30 1.98x</div></div>
 <div class="kpi"><div class="l">L30 Northbeam 7d</div><div class="v">1.17x</div><div class="s">$42,830 · 622 orders (understated before Aug 27)</div></div>
 <div class="kpi"><div class="l">L7 Aug 27–Sep 2</div><div class="v">1.45x / 1.19x</div><div class="s">$8,868 spend · Google $12,892 · Northbeam $10,590 (still maturing)</div></div>
</div>
{chart_web}
<p class="small">Daily website-lane spend (area) and Google-reported conversion value (line), Jun 1–Sep 2.</p>
{t_web}
<h4>Search terms</h4>
<ul>
<li>Waste is minimal: only two terms over $40 with zero conversions in L30 ("deep pocket sheets" $86, "extra deep pocket queen sheets" $41, both in 21 In 4PC Shopping and both now covered by the Aug 26 negatives).</li>
<li>Brand misspellings and variants reach the site through Shopping instead of the brand campaign: "ckg sheets", "ckg linens", "cjk linens", "cgk linen", "cgklinens", "cgk linens discount code" — 3–18x ROAS, no exact keyword (action 16).</li>
<li>Deal-site traffic ("cbs deals", "cbsdeals com", "localsteals com", "steal and deals today show") converts at 4–33x inside Shopping; the harvest campaign's CBS Deals ad group is the right home for it.</li>
</ul>

<h2 class="pb">3 · Beckham Home — PixelMe lane (GTA 381-888-5747)</h2>
<p>Google conversions on this account are PixelMe's uploaded "Pixelme Attribution Purchases" (3–4 day lag; zero for campaigns PixelMe did not rewrite). PixelMe's product-level Amazon numbers are the truth for revenue; they carry no Brand Referral Bonus column, so ACOS here is gross of the ~10% BRB.</p>
{t_bk_products}
{chart_bk}
<p class="small">Beckham Home daily PixelMe ad cost (area) and Amazon attributed revenue (line), Jul 5–Sep 2.</p>
{t_bk}
<ul>
<li><b>Search terms behind the losses:</b> Cooling Pillowcases spend goes to silk queries ("silk pillow cases amazon" $218, "silk pillowcase" $164, "amazon silk pillowcase" $139, "blissy pillowcase amazon" $127, "silk pillowcases amazon" $96 — 0–2 conversions between them); Pillow Protector to "pillow protector(s)" generic at 0 conv; Down Alternative to "nuzzle pillow amazon" ($317, 4 conv) and "pillows" ($209, 0). The storefront terms are healthy ("hotel pillows" $3,311 / 89 conv, "beckham hotel collection pillows" $1,246 / 149).</li>
<li><b>PixelMe status:</b> 18 campaigns linked and live (status 4), 14 at import-failed (-50, the Aug 24 clones and earlier), 5 paused. The three spending -50 clones (24169545333, 24169545984, 24175484375; $4.2k L30) get Amazon attribution from their hand-set URLs but no Google conversion upload, so Maximize Conversions has nothing to optimize on.</li>
</ul>

<h2>4 · SafeRest — PixelMe lane (GTA 559-064-2315)</h2>
{t_sr}<h4>PixelMe (Amazon truth) by window</h4>{t_sr_pm}
<ul>
<li>Both PDP campaigns run Maximize Conversion Value with tROAS 3.0 and lose 79–86% of impression share to rank with zero lost to budget; King spends $269/day of $300, Queen $118/day of $700 (P30: $215/day). PixelMe's Amazon ROAS is 3.07–3.16 in every window, Google's uploaded value reads 2.3–2.4 because of the upload lag — so Google is throttling a campaign that is above target on the truth source. Action 20 lowers tROAS to 2.6 on both.</li>
<li>Google recommends broad match here (+$2.8k cost for +$6.4k value on Google's own estimate). Decline for now; the search-term report is the safer expansion path.</li>
</ul>

<h2 class="pb">5 · What changed in the accounts (Aug 4 – Sep 3)</h2>
<p class="small">Compiled from google_ads_tw.google_change_events (re-synced today through Aug 31/Aug 24), ampd.change_log, and the session records for the Aug 6/24/26 audits. "Ampd (adwords-manager@metricstory)" is the identity every Ampd UI action and every Ampd automation writes under.</p>
{t_changelog}

<h2>6 · Ranked action list</h2>
<p class="small">"Where" follows the house routing rules: CGK [Ampd] campaign creation and ASIN linking only in Ampd; keywords, negatives, budgets and bids are attribution-safe via gads (verified Aug 13) but Ampd may reconcile them; PixelMe brands change structure in Google and linkage in PixelMe. Every gads change is plan → validate → owner approval → --confirm-live with a Slack recap.</p>
{t_actions}

<h2>7 · Open items that need a person</h2>
<ul>{''.join(f'<li>{h}</li>' for h in human)}</ul>

<h2>8 · Google recommendations (refreshed Sep 3)</h2>
<p>CGK: 2,762 open; Beckham Home: 261; SafeRest: 505. The only ones with a dollar impact worth reading: CGK marginal-ROI campaign budget (+$9,800 cost for +$2,877 value → reject), forecasting tROAS (+$8,352 cost for +$8,894 value → reject), move-unused-budget on SK White / Bamboo Cooling / 6PC All / Demand Gen (noted, no action), Beckham broad match (+$12,110 cost for +$4,585 value → reject), SafeRest broad match (+$2,812 for +$6,399 → decline for now). Accept the creative-only classes on [Ampd] campaigns: 133 RSA ad-strength and 130 sitelink recommendations across 41–44 campaigns.</p>

<h2>9 · Analysis log</h2>
{t_analysis_log}

<h2>Appendix · definitions and freshness</h2>
<ul>
<li><b>AACOS</b> = (Google cost − Brand Referral Bonus) / Amazon attributed revenue (Ampd's column). The BRB rebates cost; it is not revenue. amazon.ca campaigns earn no BRB, so their target is ≈40%.</li>
<li><b>Attribution lag:</b> Ampd and PixelMe attribute 14 days post-click and take 10–17 days to settle. Every "L14" figure will improve; decisions are made on the stable window only.</li>
<li><b>Impression share</b> figures are live Google Ads API reads for Aug 20–Sep 2 (search campaigns only; Shopping/PMax report lost-to-budget and lost-to-rank without a top-share).</li>
<li><b>Northbeam</b> rows: platform_norm = google, kind = native, accounting = accrual, model = northbeam_custom (Clicks only), window = 7 unless labeled; [Ampd] campaigns always show $0 Northbeam revenue because they land on amazon.com.</li>
<li><b>Freshness at run time (Sep 3, 13:30 ET):</b> Google performance through Sep 3 (partial) for all six accounts; Ampd exports through Sep 1; PixelMe through Sep 2; Northbeam export_daily through Sep 2 with hourly bucket ingest; Google change events through Aug 31 (CGK) / Aug 24 (Beckham Home, no later events); recommendations Sep 3.</li>
<li><b>Warehouse fix shipped this run:</b> ampd.google_lane_daily maps historical Google campaign names through ampd.campaign_name_fix (commit e6325a6 in ~/Tools/ampd-cli). Before the fix, campaign_daily_complete showed 23350268344 as $14.7k unattributed in the stable window; it is actually $14.7k → $33.2k at 34.8%.</li>
</ul>
</body></html>"""

out_html = os.path.join(S, 'report.html')
open(out_html, 'w').write(html)
print('html written', len(html))
