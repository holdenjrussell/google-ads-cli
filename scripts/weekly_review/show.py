import json, sys
name = sys.argv[1]; flt = sys.argv[2] if len(sys.argv)>2 and sys.argv[2] else None; cols = sys.argv[3].split(',') if len(sys.argv)>3 and sys.argv[3] else None
rows = json.load(open(f'data/{name}.json'))
if flt: rows = [r for r in rows if eval(flt, {}, dict(r))]
if not rows: print(f'{name}: 0 rows'); sys.exit()
cols = cols or list(rows[0].keys())
print(f'## {name} ({len(rows)} rows)'); print('\t'.join(cols))
for r in rows:
    print('\t'.join('' if r.get(c) is None else (f'{r[c]:.2f}' if isinstance(r[c],float) else str(r[c]))[:58] for c in cols))
