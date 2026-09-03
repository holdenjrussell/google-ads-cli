# Weekly review edition 2026-09-03 v2 (readability pass) — see docs/weekly-review.md. Runs from its own directory: pull.py writes ./data, this file reads it.
#!/usr/bin/env python3
"""CGK Google Ads weekly review, edition 2026-09-03 v2 (readability pass).

Reads ./data/*.json written by pull.py plus the live reads recorded in the
constants below; renders tables and inline-SVG charts. Prose is composed here.
"""
import json, os, base64, datetime
S = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(S, 'data')
def load(n): return json.load(open(os.path.join(D, n + '.json')))
def tsv(n):
    rows = [l.rstrip('\n').split('\t') for l in open(os.path.join(D, n + '.tsv'))]
    return [dict(zip(rows[0], r)) for r in rows[1:]]
NAVY, DEEP, POWDER, LINEN, GOLD, INK = '#182f5c', '#1f3d77', '#d7e7f3', '#ede6df', '#d29b28', '#121212'
def money(v, dec=0):
    if v is None: return '—'
    v = float(v); return ('-' if v < 0 else '') + '$' + f'{abs(v):,.{dec}f}'
def pct(v, dec=0):
    return '—' if v is None else f'{float(v)*100:.{dec}f}%'
def num(v): return '—' if v is None else f'{float(v):,.0f}'
def x(v, dec=2): return '—' if v is None else f'{float(v):.{dec}f}x'
def dt(s): return datetime.date.fromisoformat(s)

LOGO = os.path.join(S, 'cgk-logo-blue.png')
logo_tag = f'<img class="logo" src="data:image/png;base64,{base64.b64encode(open(LOGO,"rb").read()).decode()}" alt="CGK Linens">' if os.path.exists(LOGO) else '<div class="wordmark">CGK LINENS</div>'

# ------------------------------------------------------------------ charts
def line_area_chart(series, width=980, height=205, markers=(), title=''):
    pad_l, pad_r, pad_t, pad_b = 60, 14, 26, 34
    all_dates = sorted({d for s in series for d, _ in s['points']})
    d0, d1 = all_dates[0], all_dates[-1]; span = max(1, (d1 - d0).days)
    ymax = max(v for s in series for _, v in s['points'] if v is not None) * 1.08
    X = lambda d: pad_l + (d - d0).days / span * (width - pad_l - pad_r)
    Y = lambda v: pad_t + (1 - v / ymax) * (height - pad_t - pad_b)
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">']
    for i in range(5):
        v = ymax / 4 * i; y = Y(v)
        out.append(f'<line x1="{pad_l}" x2="{width-pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="{LINEN}"/>')
        out.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="axis">{money(v)}</text>')
    d = d0
    while d <= d1:
        if d.day in (1, 15): out.append(f'<text x="{X(d):.1f}" y="{height-12}" text-anchor="middle" class="axis">{d.strftime("%b %d")}</text>')
        d += datetime.timedelta(days=1)
    for mi, (md, label) in enumerate(markers):
        if d0 <= md <= d1:
            out.append(f'<line x1="{X(md):.1f}" x2="{X(md):.1f}" y1="{pad_t}" y2="{height-pad_b}" stroke="{INK}" stroke-dasharray="3 3" opacity="0.5"/>')
            anchor = 'end' if X(md) > width * 0.7 else 'start'; xx = X(md) - 4 if anchor == 'end' else X(md) + 4
            out.append(f'<text x="{xx:.1f}" y="{pad_t+10+12*(mi%2)}" text-anchor="{anchor}" class="axis marker">{label}</text>')
    for s in series:
        pts = [(X(d), Y(v)) for d, v in s['points'] if v is not None]
        path = 'M' + ' L'.join(f'{px:.1f},{py:.1f}' for px, py in pts)
        if s.get('kind') == 'area':
            base = height - pad_b
            out.append(f'<path d="{path} L{pts[-1][0]:.1f},{base} L{pts[0][0]:.1f},{base} Z" fill="{POWDER}"/>')
            out.append(f'<path d="{path}" fill="none" stroke="{DEEP}" stroke-width="1.2"/>')
        else:
            out.append(f'<path d="{path}" fill="none" stroke="{NAVY}" stroke-width="2" stroke-linejoin="round"/>')
    lx = pad_l
    for s in series:
        out.append(f'<rect x="{lx}" y="{height-9}" width="14" height="7" fill="{POWDER if s.get("kind")=="area" else NAVY}"/>')
        out.append(f'<text x="{lx+18}" y="{height-2}" class="axis">{s["name"]}</text>'); lx += 18 + 6.6 * len(s['name']) + 24
    out.append('</svg>'); return '\n'.join(out)

# ------------------------------------------------------------------ data
ad = {r['d']: r for r in tsv('ampd_daily_mirror')}
gl = load('cgk_daily_lane')
ampd_spend = {r['d']: float(r['spend']) for r in gl if r['lane'] == 'ampd'}
web = {r['d']: r for r in gl if r['lane'] == 'website'}
chart_ampd = line_area_chart([
    {'name': 'Google spend on [Ampd] campaigns', 'kind': 'area', 'points': [(dt(d), ampd_spend[d]) for d in sorted(ampd_spend) if d <= '2026-09-01']},
    {'name': 'Amazon revenue + Brand Referral Bonus (Ampd)', 'points': [(dt(d), float(ad[d]['rev']) + float(ad[d]['brb'])) for d in sorted(ad)]}],
    markers=[(dt('2026-07-21'), '"amazon" keywords blocked'), (dt('2026-08-21'), 'block lifted'), (dt('2026-08-26'), 'audit executed')], title='Ampd lane daily')
chart_web = line_area_chart([
    {'name': 'Google spend, website campaigns', 'kind': 'area', 'points': [(dt(d), float(r['spend'])) for d, r in sorted(web.items())]},
    {'name': 'Google-reported conversion value', 'points': [(dt(d), float(r['conv_value'])) for d, r in sorted(web.items())]}],
    markers=[(dt('2026-08-05'), 'Demand Gen live'), (dt('2026-08-26'), 'audit 08-26, budgets raised 08-27')], title='Website lane daily')
bk = {r['d']: r for r in load('pixelme_daily') if r['acct'].startswith('Thalestris')}
chart_bk = line_area_chart([
    {'name': 'Google spend (PixelMe ad cost)', 'kind': 'area', 'points': [(dt(d), float(r['cost'])) for d, r in sorted(bk.items())]},
    {'name': 'Amazon revenue attributed by PixelMe', 'points': [(dt(d), float(r['rev'])) for d, r in sorted(bk.items())]}],
    markers=[(dt('2026-08-05'), '26 non-brand campaigns launched'), (dt('2026-08-24'), '8 rebuilt')], title='Beckham Home daily')

def table(headers, rows, aligns=None, cls=''):
    aligns = aligns or ['l'] + ['r'] * (len(headers) - 1)
    h = ''.join(f'<th class="{a}">{t}</th>' for t, a in zip(headers, aligns))
    b = ''.join('<tr>' + ''.join(f'<td class="{a}">{c}</td>' for c, a in zip(r, aligns)) + '</tr>' for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'
def tag(kind):
    return f'<span class="tag {kind.lower()}">{kind}</span>'

# Ampd windows (Google spend + Ampd mirror attribution, 2026-09-03 pull)
W = {'JUL': dict(l='July', spend=71807, rev=152037, brb=14222, conv=4429, aacos=0.355),
     'AUG': dict(l='August', spend=55906, rev=131248, brb=12683, conv=3705, aacos=0.324),
     'P30': dict(l='Prior 30 (Jul 5–Aug 3)', spend=70463, rev=156117, brb=14513, conv=4494, aacos=0.347),
     'L30': dict(l='Last 30 (Aug 4–Sep 1)', spend=50764, rev=115355, brb=10947, conv=3307, aacos=0.340),
     'STABLE': dict(l='Stable 30 (Jul 21–Aug 19) — decision window', spend=56009, rev=128686, brb=11548, conv=3618, aacos=0.345),
     'L14': dict(l='Last 14 (Aug 19–Sep 1) — still maturing', spend=25036, rev=55011, brb=5043, conv=1689, aacos=0.353)}
t_ampd_windows = table(['Window', 'Spend', 'Amazon revenue', 'Bonus (BRB)', 'Orders', 'AACOS'],
    [[w['l'], money(w['spend']), money(w['rev']), money(w['brb']), num(w['conv']), f'<b>{pct(w["aacos"], 1)}</b>'] for w in W.values()])

kw = load('kw_class_weekly'); amz = {r['wk']: r for r in kw if r['is_amazon_keyword']}; gen = {r['wk']: r for r in kw if not r['is_amazon_keyword']}
t_kw = table(['Week of', '"amazon" keyword spend', 'Share of lane', 'Keywords serving', 'AACOS'],
    [[dt(w).strftime('%b %d'), money(amz[w]['cost']), f'{float(amz[w]["cost"])/(float(amz[w]["cost"])+float(gen[w]["cost"]))*100:.0f}%', num(amz[w]['kws_serving']), pct(amz[w]['aacos'])] for w in ['2026-07-06', '2026-07-13', '2026-07-27', '2026-08-10', '2026-08-17', '2026-08-24']])

ac = load('ampd_campaigns'); st = {r['campaign_id']: r for r in ac if r['win'] == 'STABLE'}; l14 = {r['campaign_id']: r for r in ac if r['win'] == 'L14'}; l30 = {r['campaign_id']: r for r in ac if r['win'] == 'L30'}
fix = {'23350268344': ((14666, 0.348), (11882, 0.348), (4098, 0.281)), '21839192355': ((1967, 0.441), (1853, 0.456), (798, 0.449))}
names = {'23350268344': '6PC King Deep Pocket KWs', '23676906151': 'Bamboo Cooling Sheets', '21496355417': '4PC Queen White (legacy "|")', '21510061819': '4PC Queen White (Manual CPC)', '21083360054': 'Storefront Deep Pocket KWs', '23864624639': 'Summer Cooling Comforters', '23859376713': 'Fleece Blankets', '23451576927': 'Duvet Cover Storefront', '21839192355': 'Canada 6PC King', '23472210370': '6PC Extra Deep Pocket King', '23758894201': 'Dorm Bed Skirt 24 in', '23576925357': 'Full XL Sheets', '22452315321': '21 Inch 6PC Storefront', '22719773443': 'RV Short Queen', '22564129915': '4PC Main Storefront', '23754299480': 'Dorm Bed Skirt 15 in', '23461114981': 'Duvet Cover New', '23582317199': 'Flex Top Split Head', '24128873457': '4PC Queen Core KWs', '22801629102': 'Cooling Bed Sheets 4PC Queen', '23864706143': 'Bulk Sheets 4PC', '22377660684': '6PC King White', '23467639163': '6PC Extra Deep Pocket', '22574740272': 'Canada 4PC Top Performers', '19876543583': 'Light Grey 2 (amazon keywords)', '21506111969': '4PC Queen White July 2024', '22821667433': 'Bamboo Product Page', '24139407325': 'RV Short Queen Core KWs', '24176957259': 'Canada Light Grey (new 08-26)', '21736166343': 'Light Grey 4 (paused 08-26)'}
verdict = {
    '23350268344': ('Keep', 'largest campaign, on target, improving'),
    '23676906151': ('Watch', 'bid cuts landed 08-26; judge 09-17'),
    '21496355417': ('Keep', 'hold at $138/d'),
    '21510061819': ('Fix', '"queen sheet set" bid $1.25 → $1.12'),
    '21083360054': ('Fix', '"extra deep queen sheets" bid $2.39 → $1.80'),
    '23864624639': ('Fix', 'revert 08-31 budget $250 → $100'),
    '23859376713': ('Cut', 'pause until Oct 1'),
    '23451576927': ('Keep', '08-26 fix working: 78% → 36%'),
    '21839192355': ('Fix', '"king sheets" bid $0.98 → $0.80 (CA target ≈40%)'),
    '23472210370': ('Scale', 'ceiling $1.40 → $1.65'),
    '23758894201': ('Keep', 'trim ceiling if L14 stays above 40%'),
    '23576925357': ('Scale', 'ceiling $1.00 → $1.25'),
    '22452315321': ('Scale', 'bid $0.83 → $1.05'),
    '22719773443': ('Scale', 'budget $24 → $75, ceiling $0.71 → $0.90'),
    '22564129915': ('Fix', 'pause "king sheets deep pocket"; ceiling $2.00 → $1.60'),
    '23754299480': ('Keep', 'dorm season ending'),
    '23461114981': ('Fix', 'ceiling $0.60 → $0.50'),
    '23582317199': ('Scale', 'ceiling $0.75 → $1.00'),
    '24128873457': ('Fix', 'switch to Manual CPC; bid the hog at $0.65'),
    '22801629102': ('Cut', 'pause — 183% AACOS, duplicates Bamboo Cooling'),
    '23864706143': ('Scale', 'ceiling $1.00 → $1.30'),
    '22377660684': ('Watch', 'amazon-keyword volume returned; judge 09-10'),
    '23467639163': ('Scale', 'ceiling $1.25 → $1.55'),
    '22574740272': ('Fix', 'ceiling $1.50 → $1.20'),
}
rows = []
for cid, r in sorted(st.items(), key=lambda kv: -float(kv[1]['cost'])):
    if float(r['cost']) < 150: continue
    if cid in fix: sc, sa = fix[cid][0]; fc, fa = fix[cid][2]
    else:
        sc, sa = float(r['cost']), r.get('aacos'); f = l14.get(cid); fc, fa = (float(f['cost']), f.get('aacos')) if f else (None, None)
    v = verdict.get(cid, ('Keep', ''))
    rows.append([f'{names.get(cid, r["campaign_name"][:40])}<br><span class="id">{cid}</span>', money(sc), pct(sa) if sa is not None else '—', pct(fa) if fa is not None else '—', tag(v[0]) + ' ' + v[1]])
t_ampd_campaigns = table(['Campaign', 'Stable spend', 'Stable AACOS', 'Last-14 AACOS<br><span class="id">maturing</span>', 'Verdict'], rows, aligns=['l', 'r', 'r', 'r', 'l'], cls='verdicts v5')

wc = load('website_campaigns'); w30 = {r['campaign_id']: r for r in wc if r['win'] == 'L30'}
l7 = {'22166226679': (1087, 1091, 741), '23836235206': (1003, 1198, 1313), '22440426630': (952, 1333, 1522), '21696634733': (858, 1169, 958), '23963684825': (760, 869, 815), '23769689251': (743, 728, 822), '23788030482': (727, 659, 428), '23747211118': (604, 1041, 1130), '23749922783': (419, 813, 806), '19342888496': (405, 115, 76), '24177022254': (359, 194, 201), '23742603974': (300, 360, 360), '13622723707': (299, 3070, 1014), '23775728849': (105, 110, 124), '23775627497': (92, 61, 160)}
live_web = {'13622723707': '$150 · tROAS 10', '19342888496': '$75 · tROAS 1.5', '21696634733': '$150 · tROAS 1.6', '22166226679': '$190 · tROAS 2.0', '22440426630': '$150 · tROAS 2.0', '23742603974': '$200 · tROAS 2.3', '23747211118': '$160 · tROAS 2.1', '23749922783': '$150 · tROAS 2.4', '23769689251': '$400 · tROAS 2.0', '23775627497': '$150 · tROAS 2.5', '23775728849': '$150 · tROAS 2.0', '23788030482': '$125 · tCPA $60', '23836235206': '$150 · tROAS 1.5', '23963684825': '$100 · tROAS 2.0', '24177022254': '$50 · Manual CPC'}
wnames = {'23788030482': 'Demand Gen / YouTube', '23836235206': 'PMax Deep Sheets + Bedskirt', '22166226679': '21 In 4PC Shopping', '22440426630': 'Queen 4PC Shopping, brand only', '19342888496': '6PC All Shopping', '21696634733': 'Queen 4PC Shopping, brand excluded', '13622723707': 'Brand search', '23747211118': 'Bed Skirts Shopping', '23963684825': 'Split King White Shopping', '23769689251': 'Pillowcases Shopping', '23749922783': 'Comforters Shopping', '23742603974': 'Bamboo Shopping', '23775627497': 'Single Flat Shopping', '24177022254': 'Harvest exact search (new 08-26)', '23775728849': 'Duvet Cover Shopping'}
wverdict = {
    '23788030482': ('Cut', 'pause; 0.65x Google / 0.52x Northbeam'),
    '23836235206': ('Watch', 'hold tROAS 1.5 to 09-10'),
    '22166226679': ('Watch', 'revert $190 → $100 if still under 1.6x on 09-10'),
    '22440426630': ('Keep', ''),
    '19342888496': ('Fix', 'value collapsed since 08-19; tROAS 1.5 → 1.8, check conversion actions'),
    '21696634733': ('Keep', ''),
    '13622723707': ('Scale', 'add misspelling keywords; tROAS 10 → 6'),
    '23747211118': ('Keep', 'the raise to $160 is working'),
    '23963684825': ('Watch', 'revert $100 → $70 if still under 1.6x on 09-10'),
    '23769689251': ('Watch', 'revert $400 → $150 if still under 1.6x on 09-10'),
    '23749922783': ('Scale', 'tROAS 2.4 → 2.1 to unlock volume'),
    '23742603974': ('Keep', ''),
    '23775627497': ('Keep', ''),
    '24177022254': ('Watch', 'losing 87% of auctions on rank; keep to 09-17'),
    '23775728849': ('Keep', ''),
}
rows = []
for cid, r in sorted(w30.items(), key=lambda kv: -float(kv[1]['spend'])):
    if float(r['spend']) < 250: continue
    s7 = l7.get(cid); v = wverdict.get(cid, ('Keep', ''))
    rows.append([f'{wnames.get(cid, r["campaign_name"][:40])}<br><span class="id">{cid} · {live_web.get(cid, "")}</span>', money(r['spend']), x(r['roas']), x(r['nb_roas7']) if r.get('nb_roas7') is not None else '—', x(s7[1]/s7[0]) if s7 else '—', x(s7[2]/s7[0]) if s7 else '—', tag(v[0]) + ' ' + v[1]])
t_web = table(['Campaign<br><span class="id">id · daily budget · target</span>', 'L30 spend', 'L30 Google', 'L30 Northbeam', 'L7 Google', 'L7 Northbeam', 'Verdict'], rows, aligns=['l', 'r', 'r', 'r', 'r', 'r', 'l'], cls='verdicts v7')

bp = load('beckham_pixelme_products'); bp30 = {r['asin']: r for r in bp if r['win'] == 'L30'}; bp14 = {r['asin']: r for r in bp if r['win'] == 'P14'}; bl14 = {r['asin']: r for r in bp if r['win'] == 'L14'}
SF = next(k for k in bp30 if k.startswith('aHR0'))
bk_rows = []
for asin, nm, v in [(SF, 'Pillow storefront (both storefront campaigns)', ('Keep', 'returns falling as spend rises: 3.28x → 2.62x; do not add budget')), ('B01LYNW421', 'Down Alternative pillows', ('Scale', 'the one non-brand winner; rebuilt in PixelMe today')), ('B0D9WXQVJS', 'Pillow protectors', ('Cut', 'rebuilt today at $150; recommend $50 + silk/satin negatives')), ('B0F2TQM32J', 'Cooling pillowcases', ('Cut', 'rebuilt today at $150; recommend $40 + silk/blissy/satin negatives')), ('B0BGTNFCN3', 'Shredded memory foam pillow', ('Cut', 'pause campaign 23969931558'))]:
    r = bp30[asin]; p = bp14.get(asin); f = bl14.get(asin)
    bk_rows.append([nm, money(r['ad_cost']), money(r['rev']), x(r['roas']), x(p['roas']) if p else '—', x(f['roas']) if f else '—', tag(v[0]) + ' ' + v[1]])
t_bk = table(['Product (PixelMe attribution)', 'L30 spend', 'Amazon revenue', 'L30 ROAS', 'Prior-14 ROAS', 'L14 ROAS', 'Verdict'], bk_rows, aligns=['l', 'r', 'r', 'r', 'r', 'r', 'l'], cls='verdicts bk')

sr = load('saferest_pixelme_products'); sr30 = {r['asin']: r for r in sr if r['win'] == 'L30'}; srp = {r['asin']: r for r in sr if r['win'] == 'P30'}
t_sr = table(['Product (PixelMe attribution)', 'Prior-30 ROAS', 'Last-30 spend', 'Amazon revenue', 'Last-30 ROAS', 'ACOS'],
    [[nm, x(srp[a]['roas']), money(sr30[a]['ad_cost']), money(sr30[a]['rev']), x(sr30[a]['roas']), pct(sr30[a]['acos'])] for a, nm in [('B003PWK2A8', 'King mattress protector'), ('B003PWNH4Q', 'Queen mattress protector')]])

decisions = [
    ('Ampd automation', 'On Aug 31 at 4 am ET something acting through Ampd raised Summer Comforters to $250/day and Bamboo Product Page to $300/day, undoing the Aug 26 cuts. Did anyone on the team do that in Ampd? If not, an Ampd automation is switched on and needs switching off.', 'Confirm, then I revert both budgets'),
    ('Demand Gen / YouTube', '$12.2k spent in the last 30 days at 0.65x Google / 0.52x Northbeam. Still 0.91x / 0.59x after the Aug 27 change to $125/day.', 'Pause, or keep as a $50/day test'),
    ('Aug 27 website budget raises', 'Pillowcases ($75 → $400), 21 In 4PC ($75 → $190) and Split King White ($55 → $100) all fell to about 1.0x in their first week at the new budgets.', 'Agree to a revert rule: back to $150 / $100 / $70 if still under 1.6x on Sep 10'),
    ('Flood Media access', 'josh@floodmedia.co has been editing the CGK account since Aug 18 (45 assets, the "BRAND #2" campaign, an ad-group tROAS). After the July compromise every external login should be deliberate.', 'Confirm it is intended'),
    ('Beckham budgets', 'The three campaigns rebuilt in PixelMe today are at $150/day like the ones they replace. Pillow Protectors (0.49x) and Cooling Pillowcases (0.28x) lose money at that level.', 'OK to cut them to $50 / $40 and add the negatives'),
    ('Google ticket', 'The "amazon" keywords have served normally since Aug 21, including the four that were still dark on Aug 24.', 'Close the ticket as resolved'),
]
t_decisions = table(['Topic', 'What the data says', 'What I need from you'], [[f'<b>{a}</b>', b, c] for a, b, c in decisions], aligns=['l', 'l', 'l'], cls='decide')

ready = [
    ('CGK Ampd', 'Pause Fleece Blankets (23859376713) until Oct 1 — 84% AACOS in every window.'),
    ('CGK Ampd', 'Pause Cooling Bed Sheets 4PC Queen (22801629102) — 183% AACOS; Bamboo Cooling already covers the terms.'),
    ('CGK Ampd', 'Bid down two hogs: "extra deep queen sheets" $2.39 → $1.80 in Storefront Deep Pocket KWs; "queen sheet set" $1.25 → $1.12 in 4PC Queen White.'),
    ('CGK Ampd', 'Convert 4PC Queen Core KWs (24128873457) to Manual CPC and bid "king size sheets on sale" at $0.65.'),
    ('CGK Ampd', 'Pause "king sheets deep pocket" in 4PC Main Storefront and lower its ceiling $2.00 → $1.60.'),
    ('CGK Ampd', 'Scale nine rank-limited campaigns at 3–25% AACOS by raising their ceilings or bids 15–35% (table in §1) and restoring RV Short Queen budgets.'),
    ('CGK Ampd', 'Canada: "king sheets" bid $0.98 → $0.80; 4PC Top Performers ceiling $1.50 → $1.20.'),
    ('CGK website', '6PC All Shopping: tROAS 1.5 → 1.8 and check its conversion actions (orders continue, value ≈ $0 since Aug 19).'),
    ('CGK website', 'Brand search: add exact keywords for the misspellings leaking into Shopping (ckg sheets, cjk linens, cgklinens…); lower tROAS 10 → 6.'),
    ('CGK website', 'Comforters Shopping: tROAS 2.4 → 2.1 (rank-limited at 2.3–2.5x).'),
    ('CGK website', 'Pause Striped Sheets Shopping (1 order on $119).'),
    ('CGK website', 'Accept Google\'s creative-only recommendations on [Ampd] campaigns (133 RSA improvements, 130 sitelinks); reject every bidding opt-in, marginal-ROI budget raise, broad match, search partners and display expansion.'),
    ('Beckham', 'Pause Adjustable Foam Pillows (23969931558) — 0.06x.'),
    ('Beckham', 'Raise Down Alternative Amazon KW (24102806289) $250 → $300 if the new PixelMe campaign confirms the 3.4x last-14 read by Sep 17.'),
    ('SafeRest', 'Lower tROAS 3.0 → 2.6 on both protector campaigns (Amazon truth 3.1x, 79–86% of auctions lost on rank).'),
]
t_ready = table(['Lane', 'Action'], [[a, b] for a, b in ready], aligns=['l', 'l'], cls='ready')

scale_rows = [
    ('6PC Extra Deep Pocket King', '23472210370', '20%', 'ceiling $1.40 → $1.65'), ('21 Inch 6PC Storefront', '22452315321', '13%', 'bid $0.83 → $1.05'),
    ('Full XL Sheets', '23576925357', '17%', 'ceiling $1.00 → $1.25'), ('Flex Top Split Head', '23582317199', '3%', 'ceiling $0.75 → $1.00'),
    ('RV Short Queen', '22719773443', '28%', 'budget $24 → $75, ceiling $0.71 → $0.90'), ('RV Short Queen Core KWs', '24139407325', '24%', 'budget $19 → $50, ceiling $0.80 → $1.00'),
    ('Bulk Sheets 4PC', '23864706143', '10%', 'ceiling $1.00 → $1.30'), ('6PC Extra Deep Pocket (B018ZT6LU0)', '23467639163', '16%', 'ceiling $1.25 → $1.55'), ('Oeko Tex Bed Sheets', '24069391339', '16%', 'ceiling $0.50 → $0.70')]
t_scale = table(['Campaign', 'Stable AACOS', 'Change'], [[f'{a}<br><span class="id">{b}</span>', c, d] for a, b, c, d in scale_rows], aligns=['l', 'r', 'l'])

changes = [
    ('Aug 13', 'CGK', 'Four "Core KWs | US" campaigns created through Ampd; budgets cut on 4PC Queen White ($400 → $138), RV Short Queen ($500 → $24), Full XL ($250 → $20).'),
    ('Aug 18 →', 'CGK', 'Flood Media (external) starts editing: 45 assets, BRAND #2 campaign, ad-group tROAS 2.25 → 2.0 on Aug 31.'),
    ('Aug 21', 'CGK', '"amazon" keyword class resumes serving after 31 days dark.'),
    ('Aug 24', 'Beckham', '8 campaigns with un-rewritten PixelMe URLs paused and rebuilt; PixelMe import starts failing on the vendor\'s side.'),
    ('Aug 26', 'CGK', 'Audit executed: 24 plans, 270 changes (cuts, bid moves, negatives, renames, new harvest and Canada campaigns, PMax/Bed Skirt targets, DG $450 → $125).'),
    ('Aug 27', 'CGK', 'Holden raises six website budgets (Pillowcases to $400, 21 In 4PC to $190, Bed Skirts to $160, Brand Excl to $150, Brand-Only to $150, SK White to $100) and sets DG to tCPA $60.'),
    ('Aug 31', 'CGK', 'Through Ampd, actor unknown: Summer Comforters $100 → $250 (+ceiling $1.25), Bamboo Product Page $30 → $300.'),
    ('Sep 3', 'Beckham', 'Three Core KW campaigns rebuilt inside PixelMe (24207685662, 24213411569, 24218651233), live at $150/day on Maximize Conversions; broken clones paused.'),
    ('Sep 3', 'data', 'Ampd join view fixed for renamed campaigns; Google change-event and recommendation feeds re-synced and now daily.'),
]
t_changes = table(['When', 'Account', 'What changed'], [[a, b, c] for a, b, c in changes], aligns=['l', 'l', 'l'])

css = f"""
@font-face {{ font-family: Raleway; src: url('file://{S}/raleway-variable.woff2') format('woff2'); font-weight: 100 900; }}
@page {{ size: Letter; margin: 15mm 13mm 16mm 13mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Raleway, 'Helvetica Neue', Arial, sans-serif; color: {INK}; background: #fff; margin: 0; font-size: 10.1pt; line-height: 1.42; }}
h1 {{ font-weight: 700; color: {NAVY}; font-size: 21pt; margin: 8px 0 2px; }}
h2 {{ font-weight: 700; color: {NAVY}; font-size: 15pt; margin: 20px 0 6px; padding-bottom: 4px; border-bottom: 2px solid {POWDER}; page-break-after: avoid; }}
h3 {{ font-weight: 600; color: {NAVY}; font-size: 11.5pt; margin: 14px 0 4px; page-break-after: avoid; }}
p {{ margin: 4px 0 8px; }}
.logo {{ width: 120px; height: auto; display: block; }}
.meta {{ color: #4a5568; font-size: 9pt; margin-bottom: 10px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin: 8px 0 12px; }}
.kpi {{ background: {POWDER}; border-radius: 6px; padding: 9px 11px; }}
.kpi .l {{ font-size: 7.6pt; letter-spacing: 0.1em; text-transform: uppercase; color: {NAVY}; font-weight: 600; }}
.kpi .v {{ font-size: 16pt; font-weight: 700; color: {NAVY}; line-height: 1.15; margin-top: 2px; }}
.kpi .s {{ font-size: 8.4pt; color: {DEEP}; margin-top: 3px; line-height: 1.35; }}
.callout {{ background: {LINEN}; color: {NAVY}; border-radius: 6px; padding: 9px 13px; margin: 8px 0 10px; }}
.gloss {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 18px; font-size: 9pt; color: #2d3748; background: #fff; border: 1px solid {LINEN}; border-radius: 6px; padding: 8px 12px; margin: 8px 0 4px; }}
.gloss b {{ color: {NAVY}; }}
table {{ border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 8.6pt; table-layout: fixed; }}
table.v5 th:nth-child(1) {{ width: 33%; }} table.v5 th:nth-child(2), table.v5 th:nth-child(3), table.v5 th:nth-child(4) {{ width: 11%; }} table.v5 th:nth-child(5) {{ width: 34%; }}
table.v7 th:nth-child(1) {{ width: 26%; }} table.v7 th:nth-child(n+2):nth-child(-n+6) {{ width: 9.5%; }} table.v7 th:nth-child(7) {{ width: 26.5%; }}
table.bk th:nth-child(1) {{ width: 24%; }} table.bk th:nth-child(n+2):nth-child(-n+6) {{ width: 10%; }} table.bk th:nth-child(7) {{ width: 26%; }}
table.full th:nth-child(1) {{ width: 36%; }} table.full th:nth-child(n+2) {{ width: 12.8%; }}
td.r {{ font-variant-numeric: tabular-nums; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th {{ background: {POWDER}; color: {NAVY}; font-weight: 700; text-align: left; padding: 5px 7px; font-size: 8.4pt; }}
td {{ padding: 4px 6px; border-bottom: 1px solid {LINEN}; vertical-align: top; overflow-wrap: anywhere; }}
td.r {{ text-align: right; white-space: nowrap; }} th.r {{ text-align: right; white-space: normal; }}
.id {{ color: #5b6472; font-size: 7.6pt; font-weight: 400; }}
.tag {{ display: inline-block; font-weight: 700; font-size: 7.6pt; letter-spacing: 0.06em; text-transform: uppercase; border-radius: 3px; padding: 1px 6px; margin-right: 5px; color: {NAVY}; background: {POWDER}; }}
.tag.cut, .tag.fix {{ background: {LINEN}; color: {NAVY}; }}
.tag.scale {{ background: {NAVY}; color: #fbf9f8; }}
.tag.watch {{ background: #fff; border: 1px solid {POWDER}; }}
table.decide td:first-child {{ width: 17%; }} table.decide td:last-child {{ width: 27%; color: {NAVY}; font-weight: 600; }}
table.ready td:first-child {{ width: 13%; white-space: nowrap; color: #4a5568; }}
.chart {{ width: 100%; height: auto; margin: 4px 0 6px; }}
.chart .axis {{ font-family: Raleway, Arial, sans-serif; font-size: 8.5px; fill: #4a5568; }}
.chart .marker {{ fill: {INK}; font-size: 8px; }}
ul {{ margin: 4px 0 8px 18px; padding: 0; }} li {{ margin: 3px 0; }}
.pb {{ page-break-before: always; }}
.small {{ font-size: 8.6pt; color: #4a5568; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
"""

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CGK Google Ads weekly review — 2026-09-03</title><style>{css}</style></head><body>
{logo_tag}
<h1>Google Ads weekly review</h1>
<div class="meta">3 September 2026 · prepared by Nova · covers CGK Linens (the Amazon-bound "Ampd" lane and the cgk.com website lane), Beckham Home and SafeRest (both attributed through PixelMe). Hotel Sheets Direct, DTC Beckham and CGK Walmart had no spend.<br>
Windows: <b>Last 30</b> = Aug 4 – Sep 2 · <b>Prior 30</b> = Jul 5 – Aug 3 · <b>Stable 30</b> = Jul 21 – Aug 19, the window Amazon-bound decisions are made on (Amazon attribution takes 10–17 days to settle) · <b>Last 14</b> is shown for direction only.</div>

<div class="kpis">
 <div class="kpi"><div class="l">CGK Amazon lane (Ampd)</div><div class="v">34.0%</div><div class="s">AACOS on $50.8k spend → $115k Amazon revenue. Target 30–35%. August closed at 32.4%; July was 35.5%.</div></div>
 <div class="kpi"><div class="l">CGK website lane</div><div class="v">1.59x</div><div class="s">Google ROAS on $36.6k spend; Northbeam says 1.17x. Spend nearly doubled vs the prior 30 days (1.98x).</div></div>
 <div class="kpi"><div class="l">Beckham Home (PixelMe)</div><div class="v">2.11x</div><div class="s">$63k → $133k Amazon revenue. Storefront 2.82x; non-brand campaigns 0.87x. Spend +81% vs prior 30.</div></div>
 <div class="kpi"><div class="l">SafeRest (PixelMe)</div><div class="v">3.10x</div><div class="s">$13.7k → $42.4k Amazon revenue, 32% ACOS, steady in every window.</div></div>
</div>

<h2>Read this first</h2>
<ul>
<li><b>The Amazon lane is healthy and smaller.</b> Spend is down 28% month over month while AACOS improved 3 points. The "amazon" keywords that Google blocked for a month are fully back (175 serving, 31% of spend); their efficiency is judged from Sep 8.</li>
<li><b>Two of the Aug 26 cuts were undone on Aug 31 through Ampd by an unknown actor.</b> That is decision 1 below.</li>
<li><b>The website lane grew fast and got less efficient:</b> Demand Gen at 0.65x, and three of the campaigns whose budgets were raised on Aug 27 fell to about 1.0x in week one.</li>
<li><b>Beckham non-brand loses money except Down Alternative pillows.</b> The three campaigns that could not link to PixelMe were rebuilt inside PixelMe today and are live; the broken copies are paused.</li>
<li><b>SafeRest is steady at 3.1x</b> and is being throttled by its own target; a lower target buys volume.</li>
</ul>
<div class="callout"><b>Net of everything below:</b> stop about $11–12k a month that runs at 0.06–0.49x, and move $6–10k a month into nine Amazon-lane campaigns at 3–25% AACOS, Down Alternative pillows at about 30% ACOS, and SafeRest at about 3x. Nothing in this document has been changed in an account except the Beckham rebuild you asked for.</div>

<h3>Decisions I need from you</h3>
{t_decisions}

<div class="gloss">
<div><b>AACOS</b> = (ad cost − Amazon's Brand Referral Bonus) ÷ Amazon revenue. Lower is better; target 30–35% (≈40% in Canada, which pays no bonus).</div>
<div><b>ROAS</b> = revenue ÷ ad cost. Google's number is last-click and over-credits brand search; Northbeam is the truth source for the website lane from Aug 27 onward.</div>
<div><b>Stable 30</b>: Amazon-bound campaigns are judged only on this window. Anything labeled "Last 14" will improve as attribution matures.</div>
<div><b>Ceiling / bid</b>: Maximize Clicks campaigns have one Max CPC ceiling; Manual CPC campaigns have keyword bids. "Rank-limited" means we lose auctions on bid, not on budget, so the lever is the ceiling or bid.</div>
</div>

<h2>1 · CGK Amazon lane (Ampd, 37 campaigns)</h2>
<p>Spend is what Google billed; revenue, bonus and orders are Ampd's Amazon attribution. Ampd's export covers 99% of the spend in every window shown.</p>
{t_ampd_windows}
{chart_ampd}
<h3>The "amazon" keywords are back</h3>
<p>Terms containing "amazon" were the efficient half of this lane (19–21% AACOS in July) until Google stopped serving them on Jul 21. They resumed on Aug 21 and by the week of Aug 24 were at 175 keywords and 31% of spend. The week-of-Aug-24 AACOS is still maturing.</p>
{t_kw}

<h3>Campaigns worth a decision (stable-window spend of $150 or more)</h3>
<p class="small">Verdicts: <b>Keep</b> = no change · <b>Watch</b> = a change is already in flight, judge on the date given · <b>Fix</b> = a bid, ceiling, budget or keyword change · <b>Cut</b> = pause · <b>Scale</b> = raise the lever named. Full campaign detail is in the appendix.</p>
{t_ampd_campaigns}

<h3>Scale set: efficient campaigns losing auctions on rank</h3>
<p>All nine run at 3–25% AACOS and lose 40–72% of available impressions to rank, under 15% to budget. Raising the ceiling or bid is the lever; budgets are not the constraint except for the two RV campaigns, which were over-cut on Aug 14.</p>
{t_scale}
<h3>Early read on the Aug 26 changes</h3>
<ul>
<li>Duvet Cover Storefront: 78% → 36% after "duvet cover set" was paused and isolated. Working.</li>
<li>Storefront Deep Pocket KWs: 26% → 43% after the +10/15/25% bid raises; "extra deep queen sheets" now costs $2.39 a click at 56%. Partial revert (bid $1.80).</li>
<li>Light Grey 2 amazon keywords: 36–44% after the +25% raise, against 19–21% before the block. Hold and judge Sep 10.</li>
<li>Full XL: still only $12 a day at the $1.00 ceiling with 47% of auctions lost on rank. Raise again.</li>
</ul>

<h2>2 · CGK website lane (cgk.com, 18 campaigns)</h2>
<div class="kpis">
 <div class="kpi"><div class="l">Last-30 spend</div><div class="v">$36,591</div><div class="s">Prior 30: $19,343 (+89%)</div></div>
 <div class="kpi"><div class="l">Google ROAS</div><div class="v">1.59x</div><div class="s">$58,115 value · 1,289 orders · prior 30 was 1.98x</div></div>
 <div class="kpi"><div class="l">Northbeam ROAS</div><div class="v">1.17x</div><div class="s">$42,830 · 622 orders · understated before Aug 27</div></div>
 <div class="kpi"><div class="l">Last 7 (Aug 27 – Sep 2)</div><div class="v">1.45x / 1.19x</div><div class="s">Google / Northbeam on $8,868 · the first fair comparison</div></div>
</div>
{chart_web}
<p>Google's conversion value is last-click and over-credits brand search (Google 7–10x, Northbeam 2.2–3.4x). Northbeam only started measuring cgk.com correctly on Aug 27, so the Last-7 columns are the fair comparison; the Last-30 Northbeam column is understated.</p>
{t_web}
<ul>
<li><b>Search-term waste is minimal:</b> only two terms over $40 with no orders, both already covered by the Aug 26 negatives.</li>
<li><b>Brand misspellings</b> ("ckg sheets", "cjk linens", "cgklinens", "cgk linens discount code") convert at 3–18x but reach the site through Shopping because the brand campaign has no exact keyword for them.</li>
<li><b>Deal-site traffic</b> ("cbs deals", "localsteals") converts at 4–33x inside Shopping; the new harvest campaign's CBS Deals ad group is the right home for it.</li>
</ul>

<h2>3 · Beckham Home (PixelMe, 381-888-5747)</h2>
<p>Spend rose 81% to $67.3k. The storefront campaigns are healthy but returns fall as spend rises. Of the non-brand products, only Down Alternative pillows make money.</p>
{t_bk}
{chart_bk}
<div class="callout"><b>Done today, on your instruction:</b> the three Core KW campaigns that PixelMe could not import (its vendor bug is still live) were rebuilt inside PixelMe, where no import is needed. They are live at $150/day on Maximize Conversions with their full keyword sets: Down Alternative 24207685662, Pillow Protectors 24213411569, Cooling Pillowcases 24218651233. The broken copies are paused. Google conversions will start appearing 3–4 days after first clicks; the ads are in Google's policy review as of this evening.</div>
<ul>
<li><b>Where the losses come from:</b> Cooling Pillowcases spend goes to silk queries ("silk pillowcase", "blissy pillowcase amazon" — 0–2 orders); Pillow Protectors to generic "pillow protector(s)" at 0 orders; Down Alternative to "nuzzle pillow amazon" (competitor, $317, 4 orders). The storefront terms are healthy ("hotel pillows" $3,311 / 89 orders).</li>
<li><b>Storefront Pillows (21144235438):</b> 82% impression share, nothing lost to budget, ROAS 3.28x → 2.62x as spend rose. Hold the budget; the floor is 2.5x.</li>
</ul>

<h2>4 · SafeRest (PixelMe, 559-064-2315)</h2>
{t_sr}
<ul>
<li>Both protector campaigns run Maximize Conversion Value with a 3.0 target and lose 79–86% of available impressions on rank, none on budget. Google sees 2.3–2.4x because PixelMe's conversion upload lags; the Amazon truth is 3.1x. Lowering the target to 2.6 buys volume at about 3x.</li>
<li>Queen PDP spend halved month over month on unchanged settings ($215 → $118 a day) — the same throttling.</li>
<li>Google suggests broad match here (+$2.8k cost for +$6.4k value, its own estimate). Decline for now; expand from the search-term report instead.</li>
</ul>

<h2>5 · Ready to execute on your OK</h2>
<p class="small">Every change goes plan → validate → your approval → live, with a Slack recap. For CGK [Ampd] campaigns, budgets, bids, ceilings, keywords and negatives are attribution-safe through gads; campaign creation stays in Ampd. Beckham and SafeRest structure changes go through Google; PixelMe owns only the product links.</p>
{t_ready}

<h2>6 · What changed in the accounts, Aug 13 – Sep 3</h2>
<p class="small">Highlights. The complete changelog by date, brand and actor lives in Obsidian under Hermes / Google Ads / Account Changelog. In Google's change history, "adwords-manager@metricstory.com" is Ampd — a person in the Ampd UI or Ampd's automation.</p>
{t_changes}

<h2 class="pb">Appendix</h2>
<h3>Sources and freshness (Sep 3, 13:30 ET)</h3>
<ul>
<li>Google Ads: warehouse `google_ads_tw`, data through Sep 2 for all six accounts; impression share, budgets and targets read live from the API for Aug 20 – Sep 2.</li>
<li>Ampd (Amazon attribution for CGK): exports through Sep 1. Coverage of Google spend 99% in every window used.</li>
<li>PixelMe (Amazon attribution for Beckham and SafeRest): through Sep 2. Its ACOS is gross of the ~10% Brand Referral Bonus.</li>
<li>Northbeam: Clicks-only model, 7-day window, accrual accounting. Valid for Google website campaigns from Aug 27 (cgk.com became a managed domain on Aug 26). [Ampd] campaigns always show $0 Northbeam revenue because they land on amazon.com.</li>
<li>Google change history and recommendations re-synced today (they had been stale since Aug 21 / Aug 24) and now sync daily.</li>
</ul>
<h3>Data fixes shipped this run</h3>
<ul>
<li>The Ampd join view mis-read the two campaigns renamed on Aug 26 as $29k of unattributed spend. Fixed; 6PC King Deep Pocket KWs is actually $14.7k → $33.2k at 34.8% in the stable window.</li>
<li>Google's bid-strategy update masks were rejected by the API in our CLI; fixed and pushed.</li>
</ul>
<h3>Google recommendations (refreshed Sep 3)</h3>
<p>CGK 2,762 open, Beckham 261, SafeRest 505. Worth reading: CGK marginal-ROI budget (+$9.8k cost for +$2.9k value → reject), forecasting tROAS (+$8.4k for +$8.9k → reject), Beckham broad match (+$12.1k for +$4.6k → reject), SafeRest broad match (+$2.8k for +$6.4k → decline for now). Accept the creative-only classes on [Ampd] campaigns (133 RSA improvements, 130 sitelinks).</p>
<h3>Analysis history</h3>
<ul>
<li><b>Aug 6</b> — first Ampd review (PDF): July compromise, "amazon" keyword block, Maximize Clicks structure, unattributed spend; AACOS definition and mirror-coverage traps fixed.</li>
<li><b>Aug 13</b> — block diagnosed as Google-side and CGK-specific; "raise bids 30%" declined; four Core KWs campaigns built.</li>
<li><b>Aug 24</b> — "Ampd vs Website" audit (18 confirmed findings, ranked list).</li>
<li><b>Aug 26</b> — audit executed (24 plans, 270 changes, five owner overrides).</li>
<li><b>Sep 3</b> — this weekly review (v2, readability pass) and the Beckham PixelMe rebuild.</li>
</ul>
<h3>Full Ampd campaign table (stable window, all campaigns above $40)</h3>
{table(['Campaign<br><span class="id">id · strategy · budget/day</span>', 'Stable spend', 'Stable AACOS', 'Last-30 spend', 'Last-30 AACOS', 'Last-14 AACOS'],
   [[f'{names.get(cid, r["campaign_name"].replace("[Ampd] ","").replace("amazon.com ","")[:44])}<br><span class="id">{cid} · {(r.get("strategy") or "").replace("TARGET_SPEND","Max Clicks").replace("MANUAL_CPC","Manual CPC")} · {money(r.get("budget"))}</span>',
     money(fix[cid][0][0] if cid in fix else r['cost']), pct(fix[cid][0][1] if cid in fix else r.get('aacos')) if (cid in fix or r.get('aacos') is not None) else '—',
     money(fix[cid][1][0] if cid in fix else (l30.get(cid) or {}).get('cost')), pct(fix[cid][1][1] if cid in fix else (l30.get(cid) or {}).get('aacos')) if (cid in fix or (l30.get(cid) or {}).get('aacos') is not None) else '—',
     pct(fix[cid][2][1] if cid in fix else (l14.get(cid) or {}).get('aacos')) if (cid in fix or (l14.get(cid) or {}).get('aacos') is not None) else '—']
    for cid, r in sorted(st.items(), key=lambda kv: -float(kv[1]['cost'])) if float(r['cost']) >= 40], aligns=['l','r','r','r','r','r'], cls='full')}
</body></html>"""
open(os.path.join(S, 'report_v2.html'), 'w').write(html); print('html v2 written', len(html))
