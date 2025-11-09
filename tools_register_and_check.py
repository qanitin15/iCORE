import http.cookiejar, urllib.request, urllib.parse, json
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
base='http://127.0.0.1:5000'
# Register a test user
payload = {'name':'Test User','email':'testuser@example.com','password':'secret123'}
req = urllib.request.Request(base + '/api/register', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type':'application/json'})
try:
    resp = opener.open(req)
    print('REGISTER', resp.getcode(), resp.read(2000).decode())
except Exception as e:
    print('REGISTER ERROR', e)
# Check session
try:
    r = opener.open(base + '/api/session_check')
    print('SESSION', r.read(2000).decode())
except Exception as e:
    print('SESSION ERROR', e)
# Fetch user
try:
    r = opener.open(base + '/api/user')
    print('USER', r.read(4000).decode())
except Exception as e:
    print('USER ERROR', e)
