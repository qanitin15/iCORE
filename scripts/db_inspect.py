import sqlite3
import os
DB='database.db'
conn=sqlite3.connect(DB)
c=conn.cursor()
print('tables:')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(' -', r[0])

print('\nusers:')
for r in c.execute('SELECT id,email,name,created_at,updated_at,wishlist,cart FROM users'):
    print(r)

print('\nproducts:')
for r in c.execute('SELECT id,title,price,category,seller_email,created_at FROM products'):
    print(r)

print('\nwishlists:')
for r in c.execute('SELECT user_id,product_id,created_at FROM wishlists'):
    print(r)

print('\ncarts:')
for r in c.execute('SELECT user_id,product_id,quantity,updated_at FROM carts'):
    print(r)

conn.close()
