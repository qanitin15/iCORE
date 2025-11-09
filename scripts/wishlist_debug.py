import requests
s = requests.Session()
BASE='http://127.0.0.1:5000'
# login
r = s.post(BASE + '/api/login', json={'email':'testuser@example.com','password':'testpass'})
print('login', r.status_code, r.text)
# toggle wishlist (choose product id 1)
r = s.post(BASE + '/api/wishlist/toggle', json={'productId': 1})
print('status', r.status_code)
print('headers', r.headers)
print('text repr', repr(r.text))
try:
    print('json:', r.json())
except Exception as e:
    print('json decode error:', e)
