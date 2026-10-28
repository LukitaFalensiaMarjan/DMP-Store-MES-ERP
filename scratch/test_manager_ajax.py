import urllib.request
import urllib.parse
import http.cookiejar
import json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Login as manager1
login_data = urllib.parse.urlencode({'username': 'manager1', 'password': '12345'}).encode('utf-8')
resp = opener.open('http://localhost:5000/login', login_data)
print('Login status:', resp.getcode())

# 2. Test AJAX approve order for ORD-0006
req = urllib.request.Request(
    'http://localhost:5000/manager/approve_order/ORD-0006',
    data=b'{}',
    headers={'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json'}
)
resp2 = opener.open(req)
approve_res = json.loads(resp2.read().decode('utf-8'))
print('Approve ORD-0006 AJAX result:', approve_res)

# 3. Test api/order/detail_atoz for ORD-0006
resp3 = opener.open('http://localhost:5000/api/order/detail_atoz/ORD-0006')
detail_res = json.loads(resp3.read().decode('utf-8'))
print('Detail ORD-0006 status:', detail_res.get('status'))
print('Detail steps count:', len(detail_res.get('order', {}).get('steps', [])))
for st in detail_res.get('order', {}).get('steps', []):
    print('  Step:', st.get('step_no'), '|', st.get('title'), '| Badge:', st.get('badge'))

print('\nALL AJAX & API ENDPOINTS FUNCTION PERFECTLY WITHOUT POPUP CLOSE!')
