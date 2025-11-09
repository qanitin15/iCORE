import sqlite3, shutil, os, time

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MAIN_DB = os.path.join(BASE, 'database.db')
RECOV_DB = os.path.join(BASE, 'recovered.db')
BACKUP = MAIN_DB + f'.bak.{int(time.time())}'

print('Main DB:', MAIN_DB)
print('Recovered DB:', RECOV_DB)

if not os.path.exists(RECOV_DB):
    print('Recovered DB not found:', RECOV_DB)
    raise SystemExit(1)
if not os.path.exists(MAIN_DB):
    print('Main DB not found:', MAIN_DB)
    raise SystemExit(1)

# Backup main DB
print('Backing up main DB to', BACKUP)
shutil.copy2(MAIN_DB, BACKUP)

def table_columns(conn, table):
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    return [r[1] for r in cur.fetchall()]

def tables_in_db(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [r[0] for r in cur.fetchall()]

m_conn = sqlite3.connect(MAIN_DB)
m_conn.execute("PRAGMA foreign_keys=ON")
r_conn = sqlite3.connect(RECOV_DB)
r_conn.execute("PRAGMA foreign_keys=OFF")

m_tables = set(tables_in_db(m_conn))
r_tables = tables_in_db(r_conn)

report = {}

for tbl in r_tables:
    print('\nProcessing table:', tbl)
    m_cols = table_columns(m_conn, tbl) if tbl in m_tables else []
    r_cols = table_columns(r_conn, tbl)
    if not r_cols:
        print(' - no columns in recovered table, skipping')
        continue

    # If table does not exist in main DB, create a simple table with TEXT columns (best-effort)
    if tbl not in m_tables:
        col_defs = ','.join([f'"{c}" TEXT' for c in r_cols])
        try:
            print(' - creating missing table in main DB:', tbl)
            m_conn.execute(f'CREATE TABLE IF NOT EXISTS "{tbl}" ({col_defs})')
            m_conn.commit()
            m_cols = table_columns(m_conn, tbl)
            m_tables.add(tbl)
        except Exception as e:
            print(' - failed to create table:', e)
            continue

    # Use intersection of columns
    use_cols = [c for c in r_cols if c in m_cols]
    if not use_cols:
        print(' - no matching columns between recovered and main table, skipping')
        continue

    col_list = ','.join([f'"{c}"' for c in use_cols])
    placeholders = ','.join(['?'] * len(use_cols))
    insert_sql = f'INSERT OR IGNORE INTO "{tbl}" ({col_list}) VALUES ({placeholders})'

    select_cols = ', '.join([f'"{c}"' for c in r_cols])
    try:
        cur = r_conn.execute(f'SELECT {select_cols} FROM "{tbl}"')
        rows = cur.fetchall()
    except Exception as e:
        print(' - failed to SELECT rows from recovered table:', e)
        rows = []

    inserted = 0
    skipped = 0

    # Build mapping index of r_cols positions to use_cols positions
    use_idx = [r_cols.index(c) for c in use_cols]

    m_conn.execute('BEGIN')
    try:
        for r in rows:
            vals = []
            for i in use_idx:
                v = r[i]
                # keep blobs/bytes as-is; sqlite3 will accept bytes for BLOB fields
                vals.append(v)
            try:
                m_conn.execute(insert_sql, vals)
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
            except Exception as e:
                print('  - insert error (skipping row):', e)
                skipped += 1
        m_conn.commit()
    except Exception as e:
        m_conn.rollback()
        print('Transaction failed for table', tbl, e)
    report[tbl] = {'rows_read': len(rows), 'inserted': inserted, 'skipped': skipped}
    print(f' - rows read: {len(rows)}, inserted: {inserted}, skipped: {skipped}')

r_conn.close()
m_conn.close()

print('\nMerge complete. Backup saved at:', BACKUP)
print('Report:')
for t, r in report.items():
    print(f" {t}: read={r['rows_read']} inserted={r['inserted']} skipped={r['skipped']}")