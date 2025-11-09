import requests
import os

BASE = 'http://127.0.0.1:5000'

s = requests.Session()

# 1) Register test user
print('Registering test user...')
resp = s.post(BASE + '/api/register',
              json={'name': 'TestUser', 'email': 'testuser@example.com', 'password': 'testpass'})
print('register', resp.status_code)
if resp.status_code == 409:
    print('user exists, trying login...')
    lr = s.post(BASE + '/api/login', json={'email': 'testuser@example.com', 'password': 'testpass'})
    print('login', lr.status_code, lr.text)

# 2) Ensure session is active via session_check
resp = s.get(BASE + '/api/session_check')
print('session_check', resp.status_code, resp.json())

# 3) Create a tiny image bytes file
img_path = 'test_img.png'
from PIL import Image

img = Image.new('RGB', (10, 10), color='blue')
img.save(img_path)

# 4) Sell product
print('Uploading product...')
with open(img_path, 'rb') as f:
    files = {'file-upload': ('test_img.png', f, 'image/png')}
    data = {'title': 'Smoke Test Item', 'price': '9.99', 'category': 'Tops', 'description': 'A tiny test item'}
    r = s.post(BASE + '/api/products/sell', files=files, data=data)
    print('sell', r.status_code, r.json())

# 5) Get products
r = s.get(BASE + '/api/products')
print('products count', r.status_code, len(r.json()))

# 6) Toggle wishlist on created product id (take first returned product id)
products = r.json()
if products:
    pid = products[0]['id']
    r = s.post(BASE + '/api/wishlist/toggle', json={'productId': pid})
    print('wishlist toggle', r.status_code, r.json())
    r = s.get(BASE + '/api/user')
    print('/api/user', r.status_code, r.json())

print('done')
