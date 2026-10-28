import urllib.request
import urllib.parse
import http.cookiejar
import re

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Login as user1
login_data = urllib.parse.urlencode({"username": "user1", "password": "12345"}).encode('utf-8')
req = urllib.request.Request("http://127.0.0.1:5000/login", data=login_data)
res = opener.open(req)

# 2. Get user dashboard
req = urllib.request.Request("http://127.0.0.1:5000/user/dashboard")
res = opener.open(req)
html = res.read().decode('utf-8')

print("HTTP Status:", res.status)

# Check elements
checks = [
    ("orderProgressStatusFilter", "id=\"orderProgressStatusFilter\"" in html),
    ("orderProgressSearchInput", "id=\"orderProgressSearchInput\"" in html),
    ("historyOrderStatusFilter", "id=\"historyOrderStatusFilter\"" in html),
    ("filter-pill-progress", "filter-pill-progress" in html),
    ("filter-pill-history", "filter-pill-history" in html),
    ("data-status-category=\"cancelled\"", "data-status-category=\"cancelled\"" in html),
    ("data-status-category=\"shipped\"", "data-status-category=\"shipped\"" in html),
    ("2. Di-ACC", "2. Di-ACC" in html),
    ("Pesanan Disetujui", "Pesanan Disetujui" in html),
    ("Pesanan Dibatalkan", "Pesanan Dibatalkan" in html),
]

for label, passed in checks:
    print(f"[{'PASS' if passed else 'FAIL'}] {label}")

# Check if any "acc manager" appears in rendered text
acc_mgr_matches = re.findall(r'acc\s+manager', html, re.IGNORECASE)
print("Occurrences of 'acc manager':", len(acc_mgr_matches), acc_mgr_matches)
