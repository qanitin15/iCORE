import socket, urllib.request
host='127.0.0.1'; port=5000
s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(1.0)
    s.connect((host,port))
    print('PORT_OPEN')
except Exception as e:
    print('PORT_CLOSED', e)
else:
    try:
        with urllib.request.urlopen(f'http://{host}:{port}', timeout=5) as r:
            data=r.read(2000).decode('utf-8', errors='replace')
            print('STATUS', r.getcode())
            print('LEN', len(data))
            print('\nPREVIEW:\n')
            print(data[:2000])
    except Exception as e:
        print('FETCH_ERROR', e)
finally:
    s.close()
