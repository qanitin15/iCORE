import sqlite3, json, os
DB = os.path.join(os.path.dirname(__file__), '..', 'database.db')
DB = os.path.abspath(DB)
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute('SELECT id,email,name,avatar,wishlist,cart FROM users')]
out = os.path.join(os.path.dirname(__file__), '..', 'users_dump.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=2, ensure_ascii=False)
print('WROTE', out)
conn.close()
