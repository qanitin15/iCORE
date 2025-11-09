import sqlite3, sys, os, json
from datetime import datetime

CORRUPT = os.path.join(os.path.dirname(__file__), '..', 'database.db.corrupt.20251005142710')
OUT_SQL = os.path.join(os.path.dirname(__file__), '..', 'recovered.sql')
OUT_DB = os.path.join(os.path.dirname(__file__), '..', 'recovered.db')

print('recover.py starting')
if not os.path.exists(CORRUPT):
    print('corrupt DB not found:', CORRUPT)
    sys.exit(2)

print('attempting to open corrupt DB in read-only mode...')
try:
    conn = sqlite3.connect('file:%s?mode=ro' % CORRUPT, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    print('reading sqlite_master...')
    c.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','index','view')")
    objs = c.fetchall()
    print('found objects:', len(objs))
    for o in objs:
        print('-', o['type'], o['name'])
    
    # Try to dump each table to JSON
    recovered = {}
    for o in objs:
        if o['type'] == 'table':
            name = o['name']
            try:
                c.execute(f"SELECT * FROM {name} LIMIT 100000")
                rows = [dict(r) for r in c.fetchall()]
                recovered[name] = rows
                print(f'dumped table {name} rows={len(rows)}')
            except Exception as e:
                print(f'failed to read table {name}:', e)
    conn.close()

    # Write out JSON and create a new DB with recovered rows
    with open(OUT_SQL, 'w', encoding='utf-8') as f:
        f.write('-- recovered dump\n')
        f.write('-- generated at %s\n' % datetime.utcnow().isoformat())
        json.dump(recovered, f, indent=2, ensure_ascii=False)

    print('wrote recovered JSON to', OUT_SQL)

    # Create a new DB and recreate tables where possible
    new = sqlite3.connect(OUT_DB)
    new.row_factory = sqlite3.Row
    nc = new.cursor()
    for name, rows in recovered.items():
        if not rows:
            continue
        # Create a simple table with columns based on first row keys as TEXT
        cols = list(rows[0].keys())
        col_defs = ','.join([f'"{c}" TEXT' for c in cols])
        try:
            nc.execute(f'CREATE TABLE IF NOT EXISTS "{name}" ({col_defs})')
        except Exception as e:
            print('failed to create table', name, e)
            continue
        placeholders = ','.join(['?'] * len(cols))
        col_list = ','.join([f'"{c}"' for c in cols])
        insert_sql = f'INSERT INTO "{name}" ({col_list}) VALUES ({placeholders})'
        for r in rows:
            vals = [str(r.get(c)) if r.get(c) is not None else None for c in cols]
            try:
                nc.execute(insert_sql, vals)
            except Exception as e:
                print('failed to insert row into', name, e)
    new.commit()
    new.close()
    print('created recovered DB at', OUT_DB)
    sys.exit(0)
except Exception as e:
    print('failed to open corrupt DB directly:', e)

# If direct read fails, try using sqlite3 backup API to copy any readable pages
print('attempting fallback backup copy...')
try:
    # Connect to source normally (may raise)
    src = sqlite3.connect(CORRUPT, timeout=10)
    dst = sqlite3.connect(OUT_DB)
    src.backup(dst, pages=0)
    dst.close()
    src.close()
    print('backup copy created', OUT_DB)
    sys.exit(0)
except Exception as e:
    print('backup copy failed:', e)
    sys.exit(3)
