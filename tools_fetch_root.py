import urllib.request, sys
url='http://127.0.0.1:5000'
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        data = r.read().decode('utf-8', errors='replace')
        print('STATUS', r.getcode())
        print('LENGTH', len(data))
        print('\nBODY PREVIEW:\n')
        print(data[:2000])
except Exception as e:
    print('ERROR', repr(e))
    sys.exit(1)
