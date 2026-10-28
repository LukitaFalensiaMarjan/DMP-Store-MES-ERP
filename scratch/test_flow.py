import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

import requests
from config import orders_col, db

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    session = requests.Session()

    # 1. Login as user1
    r = session.post(f"{BASE_URL}/login", data={"username": "user1", "password": "12345"}, allow_redirects=True)
    print("User Login Status:", r.status_code, "URL:", r.url)

    # 2. Add an item to cart using /user/add_to_cart/PRD01
    r_add = session.post(f"{BASE_URL}/user/add_to_cart/PRD01", data={"quantity": 1000}, allow_redirects=True)
    print("Add to cart status:", r_add.status_code)

    r_checkout = session.post(f"{BASE_URL}/user/checkout", data={
        "customer_name": "PT Sinar Indah B2B",
        "contact": "081234567890",
        "address": "Jl. Industri No. 10, Cikarang",
        "target_date": "2026-11-15"
    }, allow_redirects=True)
    print("Checkout status:", r_checkout.status_code)

    # 3. Check DB for new order with status 'Pending Manager Approval'
    new_order = orders_col.find_one({"status": "Pending Manager Approval"})
    assert new_order is not None, "A new order with Pending Manager Approval must exist in customer_orders!"
    order_id = new_order["order_id"]
    print(f"Created order: {order_id} with status: {new_order['status']}")

    # 4. Login as manager1
    session_mgr = requests.Session()
    r_mgr_login = session_mgr.post(f"{BASE_URL}/login", data={"username": "manager1", "password": "12345"}, allow_redirects=True)
    print("Manager Login Status:", r_mgr_login.status_code, "URL:", r_mgr_login.url)

    r_mgr = session_mgr.get(f"{BASE_URL}/manager/financial_activity")
    assert order_id in r_mgr.text, f"Order {order_id} should be visible in Manager pending ACC modal!"
    print(f"Order {order_id} is displayed in Manager pending ACC modal!")

    # 5. Test A-to-Z API endpoint
    r_api = session_mgr.get(f"{BASE_URL}/api/order/detail_atoz/{order_id}")
    print("API A-to-Z status:", r_api.status_code)
    api_data = r_api.json()
    assert api_data["status"] == "success", "API response should be success"
    steps = api_data["order"]["steps"]
    assert len(steps) == 5, "Order should have 5 chronological lifecycle steps"
    print("Audit trail 5 steps verified successfully:")
    for s in steps:
        print(f"  Step {s.get('step_no') or s.get('step')}: {s['title']} -> {s['badge']}")

    # 6. Manager ACC the order
    r_acc = session_mgr.post(f"{BASE_URL}/manager/approve_order/{order_id}", allow_redirects=True)
    print("Manager ACC status:", r_acc.status_code)
    updated_order = orders_col.find_one({"order_id": order_id})
    assert updated_order["status"] == "Approved by Manager", "Order status should be Approved by Manager"
    print("Order successfully transitioned to 'Approved by Manager'!")

    # 7. Login as supervisi1 and verify order is ready for scheduling
    session_sup = requests.Session()
    session_sup.post(f"{BASE_URL}/login", data={"username": "supervisi1", "password": "12345"}, allow_redirects=True)
    
    r_sup_orders = session_sup.get(f"{BASE_URL}/supervisi/orders")
    assert "DI-ACC MANAGER ✔" in r_sup_orders.text, "Supervisi should see DI-ACC MANAGER badge"
    assert "Jadwalkan &amp; Buat WO" in r_sup_orders.text or "Jadwalkan & Buat WO" in r_sup_orders.text, "Supervisi should see Jadwalkan & Buat WO button"
    print("Supervisi orders page displays DI-ACC MANAGER and 'Jadwalkan & Buat WO' button!")

    # 8. Clean up test order
    orders_col.delete_one({"order_id": order_id})
    print(f"Cleaned up test order {order_id}")

    print("\nALL VERIFICATIONS PASSED 100%!")

if __name__ == "__main__":
    run_tests()
