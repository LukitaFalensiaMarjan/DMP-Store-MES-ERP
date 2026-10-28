from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import check_password_hash

import ai_helper
from config import (
    users_col,
    products_col,
    inventory_col,
    machines_col,
    work_orders_col,
    orders_col,
    finance_col,
    procurement_col,
    maintenance_col,
    chats_col,
    company_settings_col,
)

app = Flask(__name__)
app.secret_key = "dmp_store_secret_key_manufaktur"


@app.context_processor
def inject_global_data():
    chat_people_count = 0
    manager_pending_acc_count = 0
    manager_shipped_count = 0
    supervisi_pending_schedule_count = 0
    manager_pending_orders = []
    manager_shipped_orders = []

    if session.get("role") == "supervisi":
        chat_people_count = len(chats_col.distinct("username"))
        supervisi_pending_schedule_count = orders_col.count_documents({
            "status": {"$in": ["Approved by Manager", "Pending Production Scheduling"]}
        })
    elif session.get("role") == "manager":
        manager_pending_orders = list(orders_col.find({
            "status": {"$in": ["Pending Manager Approval", "Pending"]}
        }).sort("_id", -1))
        manager_pending_acc_count = len(manager_pending_orders)

        manager_shipped_orders = list(orders_col.find({
            "status": "Shipped"
        }).sort("_id", -1))
        manager_shipped_count = len(manager_shipped_orders)

    return {
        "chat_people_count": chat_people_count,
        "manager_pending_acc_count": manager_pending_acc_count,
        "manager_shipped_count": manager_shipped_count,
        "supervisi_pending_schedule_count": supervisi_pending_schedule_count,
        "manager_pending_orders": manager_pending_orders,
        "manager_shipped_orders": manager_shipped_orders,
    }


@app.route('/img/<path:filename>')
def serve_img(filename):
    return send_from_directory('img', filename)


@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    role = session.get("role")
    if role == "user":
        return redirect(url_for("user_dashboard"))
    elif role == "supervisi":
        return redirect(url_for("supervisi_orders"))
    elif role == "teknisi":
        return redirect(url_for("teknisi_work_orders"))
    elif role == "manager":
        return redirect(url_for("manager_financial_activity"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["name"] = user.get("name", user["username"])
            flash(f"Selamat datang kembali, {session['name']}!", "success")
            return redirect(url_for("index"))
        else:
            flash("Username atau password salah.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda telah keluar dari sistem.", "info")
    return redirect(url_for("login"))


# ================= ROLE 1: USER =================

@app.route("/user/dashboard")
def user_dashboard():
    if session.get("role") != "user":
        return redirect(url_for("login"))

    user_doc = users_col.find_one({"username": session["username"]}) or {
        "username": session["username"],
        "name": session.get("name", "Client B2B"),
        "email": "client@company.com",
        "phone": "081234567890",
        "address": "Kawasan Industri Bandung"
    }
    products = list(products_col.find())
    raw_cart = session.get("cart", [])

    enriched_cart = []
    grand_total = 0
    max_eta_days = 1.0
    recommended_min_date = datetime.now().strftime("%Y-%m-%d")

    for item in raw_cart:
        prod = products_col.find_one({"product_id": item["product_id"]})
        if prod:
            qty = int(item["quantity"])
            subtotal = qty * prod["price_per_pcs"]
            eta_info = ai_helper.predict_order_eta(prod["product_id"], qty)

            grand_total += subtotal
            if eta_info["estimated_days"] >= max_eta_days:
                max_eta_days = eta_info["estimated_days"]
                recommended_min_date = eta_info["min_target_date"]

            enriched_cart.append({
                "product_id": prod["product_id"],
                "product_name": prod["name"],
                "name": prod["name"],
                "price_per_pcs": prod["price_per_pcs"],
                "price": prod["price_per_pcs"],
                "quantity": qty,
                "subtotal": subtotal,
                "estimated_days": eta_info["estimated_days"],
                "min_target_date": eta_info["min_target_date"],
            })

    cart_summary = {
        "grand_total": grand_total,
        "max_eta_days": max_eta_days,
        "recommended_min_date": recommended_min_date,
    }

    my_orders = list(orders_col.find({"username": session["username"]}).sort("_id", -1))
    chats = list(chats_col.find({"username": session["username"]}).sort("_id", 1))

    return render_template(
        "user_dashboard.html",
        user=user_doc,
        user_info=user_doc,
        products=products,
        cart=enriched_cart,
        cart_summary=cart_summary,
        my_orders=my_orders,
        chats=chats,
    )


@app.route("/user/add_to_cart", methods=["POST"])
@app.route("/user/add_to_cart/<product_id>", methods=["POST"])
def add_to_cart(product_id=None):
    if session.get("role") != "user":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "unauthorized"}), 401
        return redirect(url_for("login"))

    if not product_id:
        product_id = request.form.get("product_id") or (request.json.get("product_id") if request.is_json else None)

    qty = int(request.form.get("quantity") or (request.json.get("quantity") if request.is_json else 500))
    product = products_col.find_one({"product_id": product_id})

    if product:
        if qty < product["min_order"]:
            msg = f"Minimal order (MOQ) untuk {product['name']} adalah {product['min_order']} pcs."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                return jsonify({"status": "error", "message": msg}), 400
            flash(msg, "warning")
            return redirect(url_for("user_dashboard") + "#katalogSection")

        cart = session.get("cart", [])
        found = False
        for item in cart:
            if item["product_id"] == product_id:
                item["quantity"] += qty
                found = True
                break

        if not found:
            cart.append({
                "product_id": product_id,
                "name": product["name"],
                "price": product["price_per_pcs"],
                "quantity": qty,
            })

        session["cart"] = cart
        session.modified = True
        msg = f"Berhasil menambahkan {qty} pcs {product['name']} ke keranjang."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({
                "status": "success",
                "message": msg,
                "cart_count": len(cart),
                "product_name": product["name"],
                "quantity": qty
            })
        flash(msg, "success")

    return redirect(url_for("user_dashboard") + "#katalogSection")


@app.route("/user/remove_from_cart/<product_id>", methods=["GET", "POST"])
def remove_from_cart(product_id):
    if session.get("role") != "user":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "unauthorized"}), 401
        return redirect(url_for("login"))

    if "cart" in session:
        session["cart"] = [item for item in session["cart"] if item["product_id"] != product_id]
        session.modified = True
        flash("Item dihapus dari keranjang.", "info")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"status": "success", "cart_count": len(session.get("cart", []))})

    return redirect(url_for("user_dashboard") + "#katalogSection")


@app.route("/user/get_cart_data", methods=["GET"])
def user_get_cart_data():
    if session.get("role") != "user":
        return jsonify({"cart": [], "cart_summary": {}}), 401

    raw_cart = session.get("cart", [])
    enriched_cart = []
    grand_total = 0
    max_eta_days = 1.0
    recommended_min_date = datetime.now().strftime("%Y-%m-%d")

    for item in raw_cart:
        prod = products_col.find_one({"product_id": item["product_id"]})
        if prod:
            qty = int(item["quantity"])
            subtotal = qty * prod["price_per_pcs"]
            eta_info = ai_helper.predict_order_eta(prod["product_id"], qty)

            grand_total += subtotal
            if eta_info["estimated_days"] >= max_eta_days:
                max_eta_days = eta_info["estimated_days"]
                recommended_min_date = eta_info["min_target_date"]

            enriched_cart.append({
                "product_id": prod["product_id"],
                "product_name": prod["name"],
                "name": prod["name"],
                "price_per_pcs": prod["price_per_pcs"],
                "price": prod["price_per_pcs"],
                "quantity": qty,
                "subtotal": subtotal,
                "estimated_days": eta_info["estimated_days"],
                "min_target_date": eta_info["min_target_date"],
            })

    cart_summary = {
        "grand_total": grand_total,
        "max_eta_days": max_eta_days,
        "recommended_min_date": recommended_min_date,
    }
    return jsonify({
        "cart": enriched_cart,
        "cart_summary": cart_summary,
        "cart_count": len(enriched_cart)
    })


def generate_next_order_id():
    existing_orders = list(orders_col.find({}, {"order_id": 1}))
    max_num = 0
    for o in existing_orders:
        oid = o.get("order_id", "")
        if oid.startswith("ORD-"):
            try:
                num = int(oid.replace("ORD-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"ORD-{max_num + 1:04d}"


@app.route("/user/checkout", methods=["POST"])
def checkout_cart():
    if session.get("role") != "user":
        return redirect(url_for("login"))

    cart = session.get("cart", [])
    if not cart:
        flash("Keranjang belanja kosong.", "warning")
        return redirect(url_for("user_dashboard"))

    user_doc = users_col.find_one({"username": session["username"]}) or {}
    customer_name = request.form.get("customer_name") or user_doc.get("name", session["username"])
    contact = request.form.get("contact") or user_doc.get("phone", "-")
    address = request.form.get("address") or user_doc.get("address", "-")
    user_target_date = request.form.get("target_date", datetime.now().strftime("%Y-%m-%d"))

    for item in cart:
        p_id = item["product_id"]
        qty = int(item["quantity"])
        product = products_col.find_one({"product_id": p_id})
        if not product:
            continue

        eta_data = ai_helper.predict_order_eta(p_id, qty)
        total_price = qty * product["price_per_pcs"]
        prod_cost = qty * product["production_cost_per_pcs"]

        order_id = generate_next_order_id()

        new_order = {
            "order_id": order_id,
            "username": session["username"],
            "customer_name": customer_name,
            "contact": contact,
            "address": address,
            "product_id": p_id,
            "product_name": product["name"],
            "required_line_type": product.get("required_line_type", "Liquid Processing"),
            "quantity": qty,
            "total_price": total_price,
            "production_cost": prod_cost,
            "target_date": user_target_date,
            "estimated_days": eta_data["estimated_days"],
            "status": "Pending Manager Approval",
            "manager_note": None,
            "supervisor_note": None,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        orders_col.insert_one(new_order)

    session["cart"] = []
    session.modified = True
    flash("Pesanan berhasil diajukan! Menunggu persetujuan (ACC) sebelum proses penjadwalan & produksi.", "success")
    return redirect(url_for("user_dashboard"))

app.add_url_rule("/user/checkout", endpoint="user_checkout", view_func=checkout_cart, methods=["POST"])


@app.route("/user/order/edit/<order_id>", methods=["POST"])
def user_edit_order(order_id):
    if session.get("role") != "user":
        return redirect(url_for("login"))

    order = orders_col.find_one({"order_id": order_id, "username": session["username"]})
    if not order:
        flash("Order tidak ditemukan.", "danger")
        return redirect(url_for("user_dashboard"))

    product = products_col.find_one({"product_id": order["product_id"]})
    if not product:
        flash("Produk tidak ditemukan.", "danger")
        return redirect(url_for("user_dashboard"))

    try:
        new_qty = int(request.form.get("quantity", order["quantity"]))
    except (ValueError, TypeError):
        new_qty = order["quantity"]

    new_target_date = request.form.get("target_date", order["target_date"])

    if new_qty < product["min_order"]:
        flash(f"Minimal order (MOQ) untuk {product['name']} adalah {product['min_order']} pcs.", "warning")
        return redirect(url_for("user_dashboard"))

    eta_data = ai_helper.predict_order_eta(product["product_id"], new_qty)
    total_price = new_qty * product["price_per_pcs"]
    prod_cost = new_qty * product["production_cost_per_pcs"]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "quantity": new_qty,
                "target_date": new_target_date,
                "total_price": total_price,
                "production_cost": prod_cost,
                "estimated_days": eta_data["estimated_days"],
                "status": "Pending Manager Approval",
                "resubmitted_at": now_str,
                "previous_rejection_reason": order.get("rejection_reason"),
                "manager_note": None,
                "supervisor_note": None,
                "technician_note": None,
                "rejection_reason": None,
                "rejected_by": None,
                "rejected_at": None,
            }
        },
    )
    flash(f"Order {order_id} berhasil disesuaikan ({new_qty:,} pcs) dan diajukan kembali untuk di-ACC!", "success")
    return redirect(url_for("user_dashboard"))


@app.route("/user/order/cancel/<order_id>", methods=["POST"])
def user_cancel_order(order_id):
    if session.get("role") != "user":
        return redirect(url_for("login"))

    order = orders_col.find_one({"order_id": order_id, "username": session["username"]})
    if not order:
        flash("Order tidak ditemukan.", "danger")
        return redirect(url_for("user_dashboard"))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Cancelled",
                "cancelled_by": "User",
                "cancelled_at": now_str,
            }
        },
    )

    # Lepas mesin jika sebelumnya ada work order berstatus Scheduled
    wo = work_orders_col.find_one({"order_id": order_id, "status": "Scheduled"})
    if wo:
        machines_col.update_one({"machine_id": wo["machine_id"]}, {"$set": {"status": "Available"}})
        work_orders_col.update_one(
            {"wo_id": wo["wo_id"]},
            {"$set": {"status": "Cancelled", "cancel_reason": "Order dibatalkan pemesan", "cancelled_at": now_str}},
        )

    flash(f"Order {order_id} telah dibatalkan.", "info")
    return redirect(url_for("user_dashboard"))


@app.route("/user/chat_ajax", methods=["POST"])
def user_chat_ajax():
    if session.get("role") != "user":
        return jsonify({"reply": "Unauthorized", "status": "error"}), 401

    user_msg = request.form.get("message") or (request.json.get("message") if request.is_json else "")
    user_msg = (user_msg or "").strip()
    if not user_msg:
        return jsonify({"reply": "Pesan kosong.", "status": "error"}), 400

    now_str = datetime.now().strftime("%H:%M")
    sender_name = session.get("name", session["username"])
    
    # Simpan pesan user
    chats_col.insert_one({
        "username": session["username"],
        "sender": "user",
        "sender_role": "user",
        "sender_name": sender_name,
        "message": user_msg,
        "time": now_str,
        "timestamp": now_str,
    })

    # Dapatkan balasan AI Assistant
    bot_reply = ai_helper.get_chatbot_reply(user_msg, username=session.get("username"))
    
    # Simpan balasan bot
    chats_col.insert_one({
        "username": session["username"],
        "sender": "bot",
        "sender_role": "bot",
        "sender_name": "DMP AI Assistant",
        "message": bot_reply,
        "time": now_str,
        "timestamp": now_str,
    })

    return jsonify({"status": "success", "reply": bot_reply, "time": now_str})

# Endpoint alias untuk kompatibilitas frontend
app.add_url_rule("/user/chat_ajax", endpoint="send_chat", view_func=user_chat_ajax, methods=["POST"])


@app.route("/user/get_chats", methods=["GET"])
def user_get_chats():
    if session.get("role") != "user":
        return jsonify({"chats": []}), 401

    chats = list(chats_col.find({"username": session["username"]}).sort("_id", 1))
    formatted = []
    for c in chats:
        role = c.get("sender_role", c.get("sender", "user"))
        name = c.get("sender_name")
        if not name:
            if role == "user":
                name = session.get("name", "Anda")
            elif role == "bot":
                name = "Chatbot DMP"
            else:
                name = "Supervisi"
        formatted.append({
            "sender_role": role,
            "sender_name": name,
            "message": c.get("message", ""),
            "timestamp": c.get("timestamp", c.get("time", "")),
        })
    return jsonify({"chats": formatted})


# ================= ROLE 2: SUPERVISI =================

@app.route("/supervisi/dashboard")
def supervisi_dashboard():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    return redirect(url_for("supervisi_orders"))


@app.route("/supervisi/orders")
def supervisi_orders():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))

    orders = list(orders_col.find().sort("_id", -1))
    products_map = {p["product_id"]: p for p in products_col.find()}

    # Mesin yang sedang digunakan pada Work Order aktif (Scheduled / In Progress)
    busy_machine_ids = set(work_orders_col.distinct("machine_id", {"status": {"$in": ["Scheduled", "In Progress"]}}))

    raw_machines = list(machines_col.find())
    machines = []
    for m in raw_machines:
        mid = m.get("machine_id")
        m_status = m.get("status", "Available")
        health = m.get("health_score", 100)

        is_busy = (mid in busy_machine_ids) or (m_status != "Available")
        is_bad_health = health < 70
        is_selectable = (not is_busy) and (not is_bad_health)

        if mid in busy_machine_ids:
            status_label = "Sedang Digunakan"
        elif m_status != "Available":
            status_label = f"Status {m_status}"
        elif is_bad_health:
            status_label = f"Perlu Maintenance ({health}%)"
        else:
            status_label = "Siap Digunakan"

        machines.append({
            "machine_id": mid,
            "name": m.get("name", mid),
            "type": m.get("type", "Liquid Processing"),
            "status": m_status,
            "health_score": health,
            "is_selectable": is_selectable,
            "status_label": status_label,
        })

    for o in orders:
        if "required_line_type" not in o or not o["required_line_type"]:
            prod = products_map.get(o.get("product_id"))
            o["required_line_type"] = prod.get("required_line_type", "Liquid Processing") if prod else "Liquid Processing"

    ai_evals = {}
    for o in orders:
        ai_evals[o["order_id"]] = ai_helper.evaluate_order_feasibility(
            o["product_id"], o["quantity"], o["target_date"]
        )

    return render_template(
        "supervisi_orders.html",
        active_page="orders",
        orders=orders,
        machines=machines,
        ai_evals=ai_evals,
    )


def get_material_detailed_stock(material_id=None):
    products_map = {p["product_id"]: p for p in products_col.find()}
    scheduled_usage = {}
    pending_usage = {}

    # 1. Scheduled / Approved WOs
    scheduled_wos = list(work_orders_col.find({"status": "Scheduled"}))
    for wo in scheduled_wos:
        prod = products_map.get(wo.get("product_id"))
        if prod and "bom_per_pcs" in prod:
            for m_id, ratio in prod["bom_per_pcs"].items():
                amt = round(ratio * wo.get("quantity", 0), 2)
                if m_id not in scheduled_usage:
                    scheduled_usage[m_id] = {"total_kg": 0.0, "orders": []}
                scheduled_usage[m_id]["total_kg"] = round(scheduled_usage[m_id]["total_kg"] + amt, 2)
                scheduled_usage[m_id]["orders"].append({
                    "wo_id": wo.get("wo_id"),
                    "order_id": wo.get("order_id"),
                    "product_name": wo.get("product_name"),
                    "quantity": wo.get("quantity"),
                    "allocated_kg": amt,
                    "machine_id": wo.get("machine_id"),
                    "target_date": wo.get("target_date"),
                })

    # Approved orders that might not have a WO yet
    approved_orders = list(orders_col.find({"status": "Approved"}))
    scheduled_order_ids = {wo.get("order_id") for wo in scheduled_wos}
    for ord_doc in approved_orders:
        if ord_doc.get("order_id") not in scheduled_order_ids:
            prod = products_map.get(ord_doc.get("product_id"))
            if prod and "bom_per_pcs" in prod:
                for m_id, ratio in prod["bom_per_pcs"].items():
                    amt = round(ratio * ord_doc.get("quantity", 0), 2)
                    if m_id not in scheduled_usage:
                        scheduled_usage[m_id] = {"total_kg": 0.0, "orders": []}
                    scheduled_usage[m_id]["total_kg"] = round(scheduled_usage[m_id]["total_kg"] + amt, 2)
                    scheduled_usage[m_id]["orders"].append({
                        "wo_id": "-",
                        "order_id": ord_doc.get("order_id"),
                        "product_name": ord_doc.get("product_name"),
                        "quantity": ord_doc.get("quantity"),
                        "allocated_kg": amt,
                        "machine_id": "-",
                        "target_date": ord_doc.get("target_date"),
                    })

    # 2. Pending orders (Telah di-order tapi belum selesai dijadwalkan)
    pending_orders = list(orders_col.find({"status": {"$in": ["Pending Manager Approval", "Pending", "Approved by Manager"]}}))
    for ord_doc in pending_orders:
        prod = products_map.get(ord_doc.get("product_id"))
        if prod and "bom_per_pcs" in prod:
            for m_id, ratio in prod["bom_per_pcs"].items():
                amt = round(ratio * ord_doc.get("quantity", 0), 2)
                if m_id not in pending_usage:
                    pending_usage[m_id] = {"total_kg": 0.0, "orders": []}
                pending_usage[m_id]["total_kg"] = round(pending_usage[m_id]["total_kg"] + amt, 2)
                pending_usage[m_id]["orders"].append({
                    "order_id": ord_doc.get("order_id"),
                    "customer_name": ord_doc.get("customer_name"),
                    "product_name": ord_doc.get("product_name"),
                    "quantity": ord_doc.get("quantity"),
                    "needed_kg": amt,
                    "order_date": ord_doc.get("date"),
                })

    now_str = datetime.now().strftime("%d %B %Y, %H:%M:%S WIB")

    if material_id:
        mat = inventory_col.find_one({"material_id": material_id})
        if not mat:
            return None
        s_info = scheduled_usage.get(material_id, {"total_kg": 0.0, "orders": []})
        p_info = pending_usage.get(material_id, {"total_kg": 0.0, "orders": []})
        stock = float(mat.get("stock_kg", 0.0))
        in_use = float(mat.get("in_use_kg", 0.0))
        sched_kg = s_info["total_kg"]
        pend_kg = p_info["total_kg"]
        net_avail = round(stock - sched_kg, 2)
        return {
            "material_id": mat["material_id"],
            "name": mat["name"],
            "unit_price": mat.get("unit_price", 0),
            "stock_kg": stock,
            "min_threshold": mat.get("min_threshold", 0),
            "in_use_kg": in_use,
            "scheduled_kg": sched_kg,
            "pending_orders_kg": pend_kg,
            "net_available_kg": net_avail,
            "realtime_datetime": now_str,
            "scheduled_orders": s_info["orders"],
            "pending_orders": p_info["orders"],
        }
    else:
        enriched = []
        for mat in inventory_col.find():
            mid = mat["material_id"]
            s_info = scheduled_usage.get(mid, {"total_kg": 0.0, "orders": []})
            p_info = pending_usage.get(mid, {"total_kg": 0.0, "orders": []})
            stock = float(mat.get("stock_kg", 0.0))
            in_use = float(mat.get("in_use_kg", 0.0))
            sched_kg = s_info["total_kg"]
            pend_kg = p_info["total_kg"]
            net_avail = round(stock - sched_kg, 2)
            enriched.append({
                **mat,
                "in_use_kg": in_use,
                "scheduled_kg": sched_kg,
                "pending_orders_kg": pend_kg,
                "net_available_kg": net_avail,
                "realtime_datetime": now_str,
                "scheduled_orders": s_info["orders"],
                "pending_orders": p_info["orders"],
            })
        return enriched


@app.route("/api/material/detail/<material_id>", methods=["GET"])
def api_material_detail(material_id):
    if "username" not in session:
        return jsonify({"status": "unauthorized"}), 401
    detail = get_material_detailed_stock(material_id)
    if not detail:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": "success", "material": detail})


@app.route("/supervisi/inventory")
def supervisi_inventory():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    inventory = get_material_detailed_stock()
    procurements = list(procurement_col.find().sort("_id", -1))
    material_recommendations = ai_helper.ai_recommend_raw_material_needs()
    return render_template(
        "supervisi_inventory.html",
        active_page="inventory",
        inventory=inventory,
        procurements=procurements,
        material_recommendations=material_recommendations,
    )


@app.route("/supervisi/machines")
def supervisi_machines():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    machines = list(machines_col.find())
    work_orders = list(work_orders_col.find().sort("_id", -1))
    return render_template(
        "supervisi_machines.html",
        active_page="machines",
        machines=machines,
        work_orders=work_orders,
    )


@app.route("/supervisi/ai_insights")
def supervisi_ai_insights():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    return redirect(url_for("supervisi_orders"))


@app.route("/supervisi/chat/<username>")
def supervisi_chat_room(username):
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))

    all_client_users = list(users_col.find({"role": "user"}))
    distinct_usernames = [u["username"] for u in all_client_users]

    for u_chat in chats_col.distinct("username"):
        if u_chat not in distinct_usernames:
            distinct_usernames.append(u_chat)

    if not distinct_usernames:
        distinct_usernames = ["user1"]

    active_user = distinct_usernames[0] if username == "all" else username
    chats = list(chats_col.find({"username": active_user}).sort("_id", 1))

    return render_template(
        "supervisi_chat.html",
        active_page="chat",
        distinct_users=distinct_usernames,
        chat_users=all_client_users,
        active_user=active_user,
        selected_user=active_user,
        chats=chats,
    )


@app.route("/supervisi/chat/send/<username>", methods=["POST"])
def supervisi_send_message(username):
    if session.get("role") != "supervisi":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "unauthorized"}), 401
        return redirect(url_for("login"))

    msg = request.form.get("message") or (request.json.get("message") if request.is_json else "")
    msg = (msg or "").strip()
    if msg:
        now_str = datetime.now().strftime("%H:%M")
        sender_name = session.get("name", "Supervisi Produksi")
        chats_col.insert_one({
            "username": username,
            "sender": "supervisi",
            "sender_role": "supervisi",
            "sender_name": sender_name,
            "message": msg,
            "time": now_str,
            "timestamp": now_str,
        })
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({
                "status": "success",
                "message": msg,
                "time": now_str,
                "sender_name": sender_name
            })
        flash(f"Pesan terkirim ke {username}.", "success")

    return redirect(url_for("supervisi_chat_room", username=username))


@app.route("/supervisi/chat/get/<username>", methods=["GET"])
def supervisi_get_chats(username):
    if session.get("role") != "supervisi":
        return jsonify({"chats": []}), 401

    chats = list(chats_col.find({"username": username}).sort("_id", 1))
    formatted = []
    for c in chats:
        role = c.get("sender_role", c.get("sender", "user"))
        name = c.get("sender_name")
        if not name:
            if role == "supervisi":
                name = "Supervisi"
            elif role == "bot":
                name = "Chatbot DMP"
            else:
                name = "User"
        formatted.append({
            "sender_role": role,
            "sender_name": name,
            "message": c.get("message", ""),
            "timestamp": c.get("timestamp", c.get("time", "")),
        })
    return jsonify({"chats": formatted})


@app.route("/supervisi/approve/<order_id>", methods=["POST"])
def approve_order(order_id):
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))

    order = orders_col.find_one({"order_id": order_id})
    if not order:
        flash("Order tidak ditemukan.", "danger")
        return redirect(url_for("supervisi_orders"))

    product = products_col.find_one({"product_id": order["product_id"]})
    req_line = product.get("required_line_type", "Liquid Processing") if product else order.get("required_line_type", "Liquid Processing")

    machine_id = request.form.get("machine_id")
    machine_doc = machines_col.find_one({"machine_id": machine_id})

    # 1. Validasi kesesuaian lini mesin dengan tipe lini produk
    if not machine_doc or machine_doc.get("type") != req_line:
        flash(f"Gagal! Mesin {machine_id} bukan dari lini '{req_line}'. Order {order['product_name']} wajib diproses di lini '{req_line}'.", "danger")
        return redirect(url_for("supervisi_orders"))

    # 2. Validasi apakah mesin sedang digunakan pada Work Order aktif
    active_wo = work_orders_col.find_one({
        "machine_id": machine_id,
        "status": {"$in": ["Scheduled", "In Progress"]}
    })
    if machine_doc.get("status") != "Available" or active_wo:
        current_wo_id = active_wo.get("wo_id") if active_wo else "produksi aktif lain"
        flash(f"Gagal! Mesin {machine_id} sedang digunakan ({current_wo_id}) dan belum selesai oleh teknisi.", "danger")
        return redirect(url_for("supervisi_orders"))

    # 3. Validasi kondisi kesehatan mesin
    if machine_doc.get("health_score", 100) < 70:
        flash(f"Gagal! Mesin {machine_id} sedang membutuhkan maintenance (Health: {machine_doc.get('health_score')}%).", "danger")
        return redirect(url_for("supervisi_orders"))

    start_date = request.form.get("start_date")
    target_date = request.form.get("target_date")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    supervisor_name = session.get("name", "Supervisi Produksi")

    # Kunci status mesin menjadi "Assigned" agar tidak bisa dipilih order lain
    machines_col.update_one({"machine_id": machine_id}, {"$set": {"status": "Assigned"}})

    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Approved",
                "supervisor_scheduled_at": now_str,
                "supervisor_scheduled_by": supervisor_name,
                "assigned_machine_id": machine_id,
                "start_date": start_date,
                "target_date": target_date,
            }
        }
    )

    wo_count = work_orders_col.count_documents({}) + 1
    wo_id = f"WO-{wo_count:04d}"

    new_work_order = {
        "wo_id": wo_id,
        "order_id": order_id,
        "product_id": order["product_id"],
        "product_name": order["product_name"],
        "required_line_type": req_line,
        "quantity": order["quantity"],
        "machine_id": machine_id,
        "start_date": start_date,
        "target_date": target_date,
        "status": "Scheduled",
        "used_materials": [],
        "used_materials_data": [],
        "production_report": None,
    }
    work_orders_col.insert_one(new_work_order)
    flash(f"Order {order_id} berhasil dijadwalkan & Work Order {wo_id} diterbitkan ke Mesin {machine_id} ({req_line}).", "success")
    return redirect(url_for("supervisi_orders"))


@app.route("/supervisi/reject/<order_id>", methods=["POST"])
def reject_order(order_id):
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))

    note = request.form.get("supervisor_note", "Ditolak oleh Supervisi Produksi")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Rejected by Supervisor",
                "supervisor_note": note,
                "rejection_reason": note,
                "rejected_by": "Supervisi Produksi",
                "rejected_at": now_str,
            }
        },
    )
    flash(f"Order {order_id} ditolak oleh Supervisi dan status dikirimkan ke pemesan.", "warning")
    return redirect(url_for("supervisi_orders"))


@app.route("/supervisi/ship/<order_id>", methods=["POST"])
def ship_order(order_id):
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))

    order = orders_col.find_one({"order_id": order_id})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    supervisor_name = session.get("name", "Supervisi Produksi")

    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Shipped",
                "shipped_at": now_str,
                "shipped_by": supervisor_name,
                "manager_notified": True,
            }
        }
    )

    finance_col.insert_one({
        "type": "Income",
        "description": f"Penjualan Produk Order {order_id} - {order['product_name']} ({order['quantity']} pcs)",
        "amount": order["total_price"],
        "date": now_str,
    })

    flash(f"Order {order_id} berhasil dikirim (Shipped) & notifikasi diteruskan ke Manager!", "success")
    return redirect(url_for("supervisi_orders"))


@app.route("/supervisi/request_procurement", methods=["POST"])
def request_procurement():
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    material_id = request.form.get("material_id")
    qty_kg = float(request.form.get("quantity_kg", 0))

    mat = inventory_col.find_one({"material_id": material_id})
    if mat and qty_kg > 0:
        est_cost = qty_kg * mat["unit_price"]
        procurement_col.insert_one({
            "request_id": f"PR-{procurement_col.count_documents({}) + 1:03d}",
            "material_id": material_id,
            "material_name": mat["name"],
            "quantity_kg": qty_kg,
            "estimated_cost": est_cost,
            "status": "Pending Approval",
            "date": datetime.now().strftime("%Y-%m-%d"),
        })
        flash(f"Pengajuan restock {mat['name']} dikirim ke Manager.", "success")
    return redirect(url_for("supervisi_inventory"))


@app.route("/supervisi/edit_wo/<wo_id>", methods=["POST"])
def edit_work_order(wo_id):
    if session.get("role") != "supervisi":
        return redirect(url_for("login"))
    machine_id = request.form.get("machine_id")
    start_date = request.form.get("start_date")
    target_date = request.form.get("target_date")

    work_orders_col.update_one(
        {"wo_id": wo_id},
        {"$set": {"machine_id": machine_id, "start_date": start_date, "target_date": target_date}},
    )
    flash(f"Jadwal Work Order {wo_id} diperbarui.", "info")
    return redirect(url_for("supervisi_machines"))


# ================= ROLE 3: TEKNISI =================

@app.route("/teknisi/dashboard")
def teknisi_dashboard():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))
    return redirect(url_for("teknisi_work_orders"))


@app.route("/teknisi/work_orders")
def teknisi_work_orders():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))

    work_orders = list(work_orders_col.find().sort("_id", -1))
    machines = list(machines_col.find())
    inventory = list(inventory_col.find())

    wo_details = {}
    for wo in work_orders:
        rec_machine = ai_helper.recommend_machines_for_product(wo["product_id"])
        _, is_ready, shortages, requirements = ai_helper.check_material_availability(wo["product_id"], wo["quantity"])
        wo_details[wo["wo_id"]] = {
            "required_line_type": rec_machine["required_line_type"],
            "compatible_machines": rec_machine["compatible_machines"],
            "best_machine": rec_machine["best_machine"],
            "is_stock_ready": bool(is_ready),
            "shortages": shortages,
            "requirements": requirements,
        }

    return render_template(
        "teknisi_work_orders.html",
        active_page="work_orders",
        work_orders=work_orders,
        machines=machines,
        inventory=inventory,
        wo_details=wo_details,
    )


@app.route("/teknisi/accept_wo/<wo_id>", methods=["POST"])
def accept_work_order(wo_id):
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))

    wo = work_orders_col.find_one({"wo_id": wo_id})
    if not wo:
        flash("Work Order tidak ditemukan.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    machine_id = request.form.get("machine_id")
    selected_materials = request.form.getlist("selected_materials")

    product = products_col.find_one({"product_id": wo["product_id"]})
    if not product:
        flash("Data produk tidak valid.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    req_line = product.get("required_line_type", "Liquid Processing")
    machine_doc = machines_col.find_one({"machine_id": machine_id})

    if not machine_doc or machine_doc["type"] != req_line:
        flash(f"Gagal! Mesin {machine_id} bukan dari lini '{req_line}'.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    if machine_doc["status"] != "Available" and machine_id != wo.get("machine_id"):
        flash(f"Gagal! Mesin {machine_id} sedang berstatus {machine_doc['status']}.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    bom = product.get("bom_per_pcs", {})
    qty = wo["quantity"]

    if selected_materials and len(selected_materials) < len(bom):
        flash("Gagal! Seluruh bahan baku wajib pada resep BOM harus dicentang.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    if wo["status"] == "Scheduled":
        for mat_id, req_per_pcs in bom.items():
            total_needed = round(req_per_pcs * qty, 2)
            mat = inventory_col.find_one({"material_id": mat_id})
            if not mat or mat["stock_kg"] < total_needed:
                flash("Produksi Ditolak Sistem! Stok bahan baku kurang.", "danger")
                return redirect(url_for("teknisi_work_orders"))

        used_materials_summary = []
        used_materials_data = []
        for mat_id, req_per_pcs in bom.items():
            total_needed = round(req_per_pcs * qty, 2)
            inventory_col.update_one(
                {"material_id": mat_id},
                {"$inc": {"stock_kg": -total_needed, "in_use_kg": total_needed}},
            )
            mat = inventory_col.find_one({"material_id": mat_id})
            used_materials_summary.append(f"{mat['name']} ({total_needed} kg)")
            used_materials_data.append({"material_id": mat_id, "name": mat["name"], "qty_kg": total_needed})

        work_orders_col.update_one(
            {"wo_id": wo_id},
            {
                "$set": {
                    "status": "In Progress",
                    "machine_id": machine_id,
                    "used_materials": used_materials_summary,
                    "used_materials_data": used_materials_data,
                }
            },
        )
        machines_col.update_one({"machine_id": machine_id}, {"$set": {"status": "Assigned"}})
        orders_col.update_one({"order_id": wo["order_id"]}, {"$set": {"status": "In Production"}})
        flash(f"Work Order {wo_id} diterima & stok bahan baku dipotong.", "success")

    elif wo["status"] == "In Progress":
        old_machine = wo.get("machine_id")
        if old_machine and old_machine != machine_id:
            machines_col.update_one({"machine_id": old_machine}, {"$set": {"status": "Available"}})
        machines_col.update_one({"machine_id": machine_id}, {"$set": {"status": "Assigned"}})
        work_orders_col.update_one({"wo_id": wo_id}, {"$set": {"machine_id": machine_id}})
        flash(f"Mesin diubah ke {machine_id}.", "info")

    return redirect(url_for("teknisi_work_orders"))


@app.route("/teknisi/cancel_wo/<wo_id>", methods=["POST"])
def cancel_work_order(wo_id):
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))

    wo = work_orders_col.find_one({"wo_id": wo_id})
    if not wo:
        return redirect(url_for("teknisi_work_orders"))

    reason = request.form.get("cancel_reason", "Dibatalkan Teknisi")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if wo["status"] == "In Progress":
        for item in wo.get("used_materials_data", []):
            inventory_col.update_one(
                {"material_id": item["material_id"]},
                {"$inc": {"stock_kg": item["qty_kg"], "in_use_kg": -item["qty_kg"]}},
            )
        machines_col.update_one({"machine_id": wo["machine_id"]}, {"$set": {"status": "Available"}})
        work_orders_col.update_one(
            {"wo_id": wo_id},
            {"$set": {"status": "Cancelled", "used_materials": [], "used_materials_data": [], "cancel_reason": reason, "cancelled_at": now_str}},
        )
        orders_col.update_one(
            {"order_id": wo["order_id"]},
            {
                "$set": {
                    "status": "Rejected by Technician",
                    "technician_note": reason,
                    "rejection_reason": reason,
                    "rejected_by": "Teknisi Mesin (Produksi Dibatalkan)",
                    "rejected_at": now_str,
                }
            },
        )
        flash("Produksi dibatalkan & stok dikembalikan ke gudang.", "warning")

    elif wo["status"] == "Scheduled":
        machines_col.update_one({"machine_id": wo["machine_id"]}, {"$set": {"status": "Available"}})
        work_orders_col.update_one(
            {"wo_id": wo_id},
            {"$set": {"status": "Rejected by Technician", "cancel_reason": reason, "cancelled_at": now_str}},
        )
        orders_col.update_one(
            {"order_id": wo["order_id"]},
            {
                "$set": {
                    "status": "Rejected by Technician",
                    "technician_note": reason,
                    "rejection_reason": reason,
                    "rejected_by": "Teknisi Mesin",
                    "rejected_at": now_str,
                }
            },
        )
        flash("Work Order ditolak dan status order dikirimkan ke pemesan.", "warning")

    return redirect(url_for("teknisi_work_orders"))


@app.route("/teknisi/execute/<wo_id>", methods=["POST"])
def execute_work_order(wo_id):
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))

    wo = work_orders_col.find_one({"wo_id": wo_id})
    if not wo:
        flash("Work Order tidak ditemukan.", "danger")
        return redirect(url_for("teknisi_work_orders"))

    good_qty = int(request.form.get("good_qty", 0))
    reject_qty = int(request.form.get("reject_qty", 0))
    total_produced = good_qty + reject_qty

    temp = float(request.form.get("sensor_temp", 45.0))
    vib = float(request.form.get("sensor_vibration", 2.0))
    curr = float(request.form.get("sensor_current", 12.0))

    sensor_analysis = ai_helper.analyze_sensor_condition(temp, vib, curr)

    # Sinkronisasi Degradasi Kesehatan Mesin (Wear & Tear) Berdasarkan Pemakaian:
    machine_doc = machines_col.find_one({"machine_id": wo["machine_id"]}) or {}
    old_health = machine_doc.get("health_score", 100)
    old_wos = machine_doc.get("total_completed_wos", 0)
    old_qty = machine_doc.get("total_units_produced", 0)

    # 1. Base cycle wear: 4% per eksekusi pengerjaan Work Order
    cycle_wear = 4.0
    # 2. Volume output wear: beban gesekan mekanis berbanding lurus kuantitas produk (0.5% per 100 pcs)
    volume_wear = round((total_produced / 100.0) * 0.5, 1)
    # 3. Penalti sensor jika suhu / getaran / arus beban berlebih saat pengerjaan
    sensor_penalty = round(sensor_analysis.get("penalty", 0) * 0.4, 1)

    total_wear = cycle_wear + volume_wear + sensor_penalty
    new_health = max(20, round(old_health - total_wear))

    plan_qty = wo["quantity"]
    availability = 95.0
    performance = min(110.0, round((total_produced / plan_qty) * 100, 1)) if plan_qty > 0 else 100.0
    quality = round((good_qty / total_produced) * 100, 1) if total_produced > 0 else 100.0
    oee = round((availability * performance * quality) / 10000.0, 1)

    production_report = {
        "good_qty": good_qty,
        "reject_qty": reject_qty,
        "total_produced": total_produced,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee_percentage": oee,
        "sensor_data": {"temperature_c": temp, "vibration_mm_s": vib, "current_amp": curr},
        "sensor_analysis": sensor_analysis,
        "wear_deducted": total_wear,
    }

    for item in wo.get("used_materials_data", []):
        inventory_col.update_one(
            {"material_id": item["material_id"]},
            {"$inc": {"in_use_kg": -item["qty_kg"]}},
        )

    work_orders_col.update_one(
        {"wo_id": wo_id},
        {"$set": {"status": "Completed", "production_report": production_report}},
    )
    orders_col.update_one({"order_id": wo["order_id"]}, {"$set": {"status": "Completed"}})
    machines_col.update_one(
        {"machine_id": wo["machine_id"]},
        {
            "$set": {
                "status": "Available",
                "health_score": new_health,
                "total_completed_wos": old_wos + 1,
                "total_units_produced": old_qty + total_produced,
                "last_sensor": {"temperature_c": temp, "vibration_mm_s": vib, "current_amp": curr},
            }
        },
    )

    order_doc = orders_col.find_one({"order_id": wo["order_id"]})
    if order_doc:
        finance_col.insert_one({
            "type": "Expense",
            "description": f"Biaya Produksi Work Order {wo_id} - {wo['product_name']}",
            "amount": order_doc["production_cost"],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    flash(f"Orderan Selesai (OEE: {oee}%) & diteruskan ke Supervisi!", "success")
    return redirect(url_for("teknisi_work_orders"))


@app.route("/teknisi/machine_sensors", methods=["GET", "POST"])
def teknisi_machine_sensors():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))

    machines = list(machines_col.find())
    analysis_result = None
    selected_machine = None

    if request.method == "POST":
        machine_id = request.form.get("machine_id")
        temp = float(request.form.get("sensor_temp", 45.0))
        vib = float(request.form.get("sensor_vibration", 2.0))
        curr = float(request.form.get("sensor_current", 12.0))

        cur_m = machines_col.find_one({"machine_id": machine_id}) or {}
        base_h = cur_m.get("health_score", 100)
        analysis_result = ai_helper.analyze_sensor_condition(temp, vib, curr, base_health=base_h)
        new_health = analysis_result["calculated_health"]

        machines_col.update_one(
            {"machine_id": machine_id},
            {
                "$set": {
                    "health_score": new_health,
                    "last_sensor": {"temperature_c": temp, "vibration_mm_s": vib, "current_amp": curr},
                }
            },
        )
        selected_machine = machines_col.find_one({"machine_id": machine_id})
        flash("Data sensor diperbarui!", "success")

    return render_template(
        "teknisi_machine_sensors.html",
        active_page="machine_sensors",
        machines=machines,
        analysis_result=analysis_result,
        selected_machine=selected_machine,
    )


@app.route("/teknisi/maintenance_recommendations")
def teknisi_maintenance_recommendations():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))
    machine_priorities = ai_helper.ai_recommend_maintenance_priority()
    machines = list(machines_col.find())
    return render_template(
        "teknisi_maintenance_recommendations.html",
        active_page="maintenance_recommendations",
        machine_priorities=machine_priorities,
        machines=machines,
    )


@app.route("/teknisi/maintenance_requests")
def teknisi_maintenance_requests():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))
    machines = list(machines_col.find())
    maintenance_list = list(maintenance_col.find().sort("_id", -1))
    return render_template(
        "teknisi_maintenance_requests.html",
        active_page="maintenance_requests",
        machines=machines,
        maintenance_list=maintenance_list,
    )


@app.route("/teknisi/request_maintenance", methods=["POST"])
def request_maintenance():
    if session.get("role") != "teknisi":
        return redirect(url_for("login"))
    machine_id = request.form.get("machine_id")
    maint_type = request.form.get("maintenance_type")
    duration = int(request.form.get("duration_hours", 0))
    cost = float(request.form.get("estimated_cost", 0))

    maintenance_col.insert_one({
        "request_id": f"MAINT-{maintenance_col.count_documents({}) + 1:03d}",
        "machine_id": machine_id,
        "maintenance_type": maint_type,
        "duration_hours": duration,
        "estimated_cost": cost,
        "status": "Pending Manager Approval",
        "date": datetime.now().strftime("%Y-%m-%d"),
    })
    flash("Pengajuan maintenance dikirim ke Manager.", "success")
    return redirect(url_for("teknisi_maintenance_requests"))


# ================= ROLE 4: MANAGER =================

@app.route("/manager/approve_order/<order_id>", methods=["POST"])
def manager_approve_order(order_id):
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    note = request.form.get("manager_note", "Disetujui oleh Manager.")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    manager_name = session.get("name", "Executive Manager")

    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Approved by Manager",
                "manager_approved_at": now_str,
                "manager_approved_by": manager_name,
                "manager_note": note,
            }
        }
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        rem_count = orders_col.count_documents({"status": "Pending Manager Approval"})
        return jsonify({
            "status": "success",
            "message": f"Order {order_id} berhasil di-ACC oleh Manager dan diteruskan ke Supervisi untuk penjadwalan produksi.",
            "order_id": order_id,
            "remaining_pending": rem_count
        })
    flash(f"Order {order_id} berhasil di-ACC oleh Manager dan diteruskan ke Supervisi untuk penjadwalan produksi.", "success")
    return redirect(request.referrer or url_for("manager_financial_activity"))


@app.route("/manager/reject_order/<order_id>", methods=["POST"])
def manager_reject_order(order_id):
    if session.get("role") != "manager":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"status": "unauthorized"}), 401
        return redirect(url_for("login"))

    reason = request.form.get("rejection_reason", "Ditolak oleh Manager.")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    orders_col.update_one(
        {"order_id": order_id},
        {
            "$set": {
                "status": "Rejected by Manager",
                "rejection_reason": reason,
                "rejected_by": "Manager",
                "rejected_at": now_str,
            }
        }
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        rem_count = orders_col.count_documents({"status": "Pending Manager Approval"})
        return jsonify({
            "status": "success",
            "message": f"Order {order_id} telah ditolak oleh Manager.",
            "order_id": order_id,
            "remaining_pending": rem_count
        })
    flash(f"Order {order_id} telah ditolak oleh Manager dan status penolakan dikirimkan ke pemesan.", "warning")
    return redirect(request.referrer or url_for("manager_financial_activity"))


def get_order_full_audit_trail(order_id):
    order = orders_col.find_one({"order_id": order_id})
    if not order:
        return None

    wo = work_orders_col.find_one({"order_id": order_id})
    product = products_col.find_one({"product_id": order.get("product_id")})
    machine = machines_col.find_one({"machine_id": wo.get("machine_id")}) if wo else None
    if not machine and order.get("assigned_machine_id"):
        machine = machines_col.find_one({"machine_id": order.get("assigned_machine_id")})

    total_price = float(order.get("total_price", 0))
    prod_cost = float(order.get("production_cost", 0))
    net_profit = total_price - prod_cost
    margin_pct = round((net_profit / total_price) * 100, 1) if total_price > 0 else 0.0

    # Step 1: Pemesanan Masuk Klien
    s1 = {
        "step_no": 1,
        "title": "Pemesanan Masuk (Client B2B)",
        "subtitle": "Klien melakukan pemesanan melalui katalog sistem B2B.",
        "timestamp": order.get("date", "-"),
        "badge": "Diajukan",
        "badge_color": "success",
        "details": {
            "ID Order": order.get("order_id"),
            "Pemesan": f"{order.get('customer_name', '-')} ({order.get('username', '-')})",
            "Kontak": order.get("contact", "-"),
            "Alamat Pengiriman": order.get("address", "-"),
            "Produk Dipesan": f"{order.get('product_name', '-')} ({order.get('product_id', '-')})",
            "Kuantitas": f"{order.get('quantity', 0):,} pcs",
            "Nilai Transaksi": f"Rp {total_price:,.0f}",
            "Target Tanggal Klien": order.get("target_date", "-"),
            "Estimasi Waktu AI": f"{order.get('estimated_days', '-')} hari kerja",
        }
    }

    # Step 2: Persetujuan Manajer (ACC Manager)
    is_m_acc = bool(order.get("manager_approved_at") or order.get("status") in ["Approved by Manager", "Approved", "In Production", "Completed", "Shipped"])
    is_m_rej = (order.get("status") == "Rejected by Manager" or order.get("rejected_by") == "Manager")
    m_status_badge = "Ditolak Manager" if is_m_rej else ("Disetujui (ACC)" if is_m_acc else "Menunggu ACC")
    m_badge_color = "danger" if is_m_rej else ("success" if is_m_acc else "warning")

    s2 = {
        "step_no": 2,
        "title": "Persetujuan Manajerial (ACC Manager)",
        "subtitle": "Evaluasi kelayakan margin bisnis dan persetujuan komersial pabrik.",
        "timestamp": order.get("manager_approved_at") or (order.get("rejected_at") if is_m_rej else (order.get("date") if is_m_acc else "-")),
        "badge": m_status_badge,
        "badge_color": m_badge_color,
        "details": {
            "Status Persetujuan": m_status_badge,
            "Disetujui Oleh": order.get("manager_approved_by", "Manager") if is_m_acc else "-",
            "Catatan Manajer": order.get("manager_note") or order.get("rejection_reason") or "Order layak secara finansial & margin keuntungan memadai.",
            "Estimasi Margin Profit": f"Rp {net_profit:,.0f} ({margin_pct}%)",
            "Diteruskan Ke": "Supervisi Produksi untuk Penjadwalan Lini Mesin" if is_m_acc else "Pemesan (Ditolak)",
        }
    }

    # Step 3: Penjadwalan & Alokasi Mesin Supervisi
    is_sched = bool(wo or order.get("status") in ["Approved", "In Production", "Completed", "Shipped"])
    is_s_rej = (order.get("status") in ["Rejected", "Rejected by Supervisor"])
    s_badge = "Ditolak Supervisi" if is_s_rej else ("Terjadwal" if is_sched else "Menunggu Penjadwalan")
    s_badge_color = "danger" if is_s_rej else ("info" if is_sched else "secondary")

    m_id = wo.get("machine_id") if wo else (order.get("assigned_machine_id") or "-")
    m_name = machine.get("name") if machine else f"Lini {order.get('required_line_type', '-')}"
    m_health = f"{machine.get('health_score')}%" if machine else "-"

    s3 = {
        "step_no": 3,
        "title": "Penjadwalan Produksi & Alokasi Lini Mesin (Supervisi)",
        "subtitle": "Supervisi memverifikasi kesesuaian lini produk dan menugaskan mesin.",
        "timestamp": order.get("supervisor_scheduled_at") or (wo.get("start_date") if wo else "-"),
        "badge": s_badge,
        "badge_color": s_badge_color,
        "details": {
            "Lini Produksi": order.get("required_line_type", "-"),
            "Mesin Ditugaskan": f"{m_id} - {m_name} (Kesehatan: {m_health})",
            "Jadwal Pelaksanaan": f"{wo.get('start_date', '-')} s/d {wo.get('target_date', '-')}" if wo else "-",
            "ID Work Order Diterbitkan": wo.get("wo_id", "-") if wo else "-",
            "Disupervisi Oleh": order.get("supervisor_scheduled_by", "Supervisi Produksi") if is_sched else "-",
        }
    }

    # Step 4: Eksekusi Produksi & QC Teknisi
    is_prod_done = bool(wo and wo.get("status") == "Completed" or order.get("status") in ["Completed", "Shipped"])
    is_t_rej = (order.get("status") == "Rejected by Technician")
    prod_report = wo.get("production_report") if wo else None

    t_badge = "Ditolak Teknisi" if is_t_rej else ("Selesai (QC Passed)" if is_prod_done else ("Sedang Berjalan" if wo and wo.get("status") == "In Progress" else "Dalam Antrean"))
    t_badge_color = "danger" if is_t_rej else ("success" if is_prod_done else "primary")

    used_mat_str = ", ".join(wo.get("used_materials", [])) if (wo and wo.get("used_materials")) else "Bahan baku formulasi terpotong otomatis dari Gudang"
    sensor_str = "-"
    if prod_report and "sensor_data" in prod_report:
        sd = prod_report["sensor_data"]
        sensor_str = f"Suhu: {sd.get('temperature_c')}°C | Getaran: {sd.get('vibration_mm_s')} mm/s | Arus: {sd.get('current_amp')}A"

    s4 = {
        "step_no": 4,
        "title": "Eksekusi Produksi & Quality Control (Teknisi Mesin)",
        "subtitle": "Teknisi memproses bahan baku, memonitor sensor IoT, dan mencatat OEE.",
        "timestamp": wo.get("target_date") if wo else "-",
        "badge": t_badge,
        "badge_color": t_badge_color,
        "details": {
            "ID Work Order": wo.get("wo_id", "-") if wo else "-",
            "Status Pengerjaan": t_badge,
            "Output Produk Baik": f"{prod_report.get('good_qty', order.get('quantity')):,} pcs" if prod_report else f"{order.get('quantity', 0):,} pcs",
            "Produk Cacat (Reject)": f"{prod_report.get('reject_qty', 0):,} pcs" if prod_report else "0 pcs",
            "Efektivitas Mesin (OEE)": f"{prod_report.get('oee_percentage', 95.0)}%" if prod_report else "95.0%",
            "Telemetri Sensor IoT": sensor_str,
            "Bahan Baku Terpakai": used_mat_str,
            "Pengurangan Aus Mesin": f"-{prod_report.get('wear_deducted', 6.0)}%" if prod_report else "-",
        }
    }

    # Step 5: Pengiriman (Shipping) Supervisi
    is_shipped = (order.get("status") == "Shipped")
    ship_badge = "Terkirim (Shipped)" if is_shipped else ("Siap Dikirim" if is_prod_done else "Menunggu Selesai")
    ship_badge_color = "dark" if is_shipped else ("warning" if is_prod_done else "secondary")

    s5 = {
        "step_no": 5,
        "title": "Pengiriman Pesanan (Shipping)",
        "subtitle": "Supervisi memverifikasi pengiriman barang ke ekspedisi/klien.",
        "timestamp": order.get("shipped_at") or (order.get("date") if is_shipped else "-"),
        "badge": ship_badge,
        "badge_color": ship_badge_color,
        "details": {
            "Status Pengiriman": ship_badge,
            "Tanggal / Waktu Kirim": order.get("shipped_at") or (order.get("date") if is_shipped else "-"),
            "Dikonfirmasi Oleh": order.get("shipped_by", "Supervisi Produksi") if is_shipped else "-",
            "Pendapatan Masuk Kas": f"Rp {total_price:,.0f} (Tercatat di Buku Kas)",
            "Notifikasi ke Manager": "Terkirim & Tersinkronisasi" if is_shipped else "Belum",
        }
    }

    return {
        "order_id": order.get("order_id"),
        "customer_name": order.get("customer_name", "-"),
        "username": order.get("username", "-"),
        "contact": order.get("contact", "-"),
        "address": order.get("address", "-"),
        "product_id": order.get("product_id"),
        "product_name": order.get("product_name"),
        "category": product.get("category", "-") if product else "-",
        "quantity": order.get("quantity", 0),
        "total_price": total_price,
        "production_cost": prod_cost,
        "net_profit": net_profit,
        "margin_percentage": margin_pct,
        "status": order.get("status"),
        "target_date": order.get("target_date"),
        "order_date": order.get("date"),
        "steps": [s1, s2, s3, s4, s5]
    }


@app.route("/api/order/detail_atoz/<order_id>", methods=["GET"])
def api_order_detail_atoz(order_id):
    if "username" not in session:
        return jsonify({"status": "unauthorized"}), 401
    data = get_order_full_audit_trail(order_id)
    if not data:
        return jsonify({"status": "not_found", "message": "Order tidak ditemukan"}), 404
    return jsonify({"status": "success", "order": data})


def get_company_financial_summary():
    setting = company_settings_col.find_one({"key": "base_capital_cash"})
    if not setting:
        base_capital_cash = 3870233000
        company_settings_col.update_one(
            {"key": "base_capital_cash"},
            {"$set": {"base_capital_cash": base_capital_cash}},
            upsert=True
        )
    else:
        base_capital_cash = float(setting.get("base_capital_cash", 3870233000))

    # Urutkan secara kronologis (dari awal) untuk kalkulasi saldo kas berjalan (Running Balance)
    chrono_records = list(finance_col.find().sort("_id", 1))
    running_balance = base_capital_cash
    for r in chrono_records:
        if r.get("type") == "Income":
            running_balance += r.get("amount", 0)
        else:
            running_balance -= r.get("amount", 0)
        r["running_balance"] = running_balance

    # Balikkan urutan agar transaksi paling baru berada di baris teratas pada tabel UI
    financial_records = list(reversed(chrono_records))

    sales_records = [r for r in financial_records if "Penjualan" in r.get("description", "") or r.get("type") == "Income"]
    maintenance_records = [r for r in financial_records if "Maintenance" in r.get("description", "")]
    material_records = [r for r in financial_records if "Bahan Baku" in r.get("description", "")]
    production_records = [r for r in financial_records if "Biaya Produksi" in r.get("description", "")]

    total_sales_income = sum(item.get("amount", 0) for item in sales_records)
    total_expense = sum(item.get("amount", 0) for item in financial_records if item.get("type") == "Expense")
    net_profit = total_sales_income - total_expense

    # Saldo kas perusahaan ter-sinkronisasi penuh: Kas Awal + Total Pemasukan - Total Pengeluaran
    company_cash = base_capital_cash + total_sales_income - total_expense

    return {
        "base_capital_cash": base_capital_cash,
        "company_cash": company_cash,
        "financial_records": financial_records,
        "sales_records": sales_records,
        "maintenance_records": maintenance_records,
        "material_records": material_records,
        "production_records": production_records,
        "total_sales_income": total_sales_income,
        "total_expense": total_expense,
        "net_profit": net_profit,
    }


@app.route("/manager/financial_activity")
def manager_financial_activity():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    fin_summary = get_company_financial_summary()

    # Valuasi Stok Bahan Baku di Gudang
    inventory_items = list(inventory_col.find())
    inventory_valuation = sum(item.get("stock_kg", 0) * item.get("unit_price", 0) for item in inventory_items)

    # Nilai Pesanan Sedang Berjalan (Work In Progress / WIP)
    wip_orders = list(orders_col.find({"status": {"$in": ["Pending", "Approved", "In Production"]}}))
    active_wip_value = sum(item.get("total_price", 0) for item in wip_orders)

    # Total Estimasi Aset Lancar Perusahaan (Kas Sinkron + Valuasi Bahan Baku + WIP)
    total_liquid_assets = fin_summary["company_cash"] + inventory_valuation + active_wip_value

    # Business KPIs
    total_orders_count = orders_col.count_documents({})
    completed_orders = list(orders_col.find({"status": {"$in": ["Completed", "Shipped"]}}))
    completed_orders_count = len(completed_orders)
    total_units_sold = sum(item.get("quantity", 0) for item in completed_orders)
    avg_order_value = round(fin_summary["total_sales_income"] / completed_orders_count) if completed_orders_count > 0 else 0
    gross_margin_pct = round((fin_summary["net_profit"] / fin_summary["total_sales_income"]) * 100, 1) if fin_summary["total_sales_income"] > 0 else 0.0

    return render_template(
        "manager_financial.html",
        active_page="financial",
        financial_records=fin_summary["financial_records"],
        sales_records=fin_summary["sales_records"],
        maintenance_records=fin_summary["maintenance_records"],
        material_records=fin_summary["material_records"],
        production_records=fin_summary["production_records"],
        total_sales_income=fin_summary["total_sales_income"],
        total_expense=fin_summary["total_expense"],
        net_profit=fin_summary["net_profit"],
        base_capital_cash=fin_summary["base_capital_cash"],
        company_cash=fin_summary["company_cash"],
        inventory_valuation=inventory_valuation,
        active_wip_value=active_wip_value,
        total_liquid_assets=total_liquid_assets,
        total_orders_count=total_orders_count,
        completed_orders_count=completed_orders_count,
        total_units_sold=total_units_sold,
        avg_order_value=avg_order_value,
        gross_margin_pct=gross_margin_pct,
    )


@app.route("/manager/financial_charts")
def manager_financial_charts():
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    fin_analysis = ai_helper.ai_analyze_financial_health()
    prod_analysis = ai_helper.ai_analyze_product_performance()
    fin_summary = get_company_financial_summary()
    company_cash = fin_summary["company_cash"]
    base_capital_cash = fin_summary["base_capital_cash"]

    # Chart 1: Product performance
    prod_labels = [p["name"] for p in prod_analysis["product_stats"]]
    prod_revenues = [p["total_revenue"] for p in prod_analysis["product_stats"]]
    prod_quantities = [p["total_qty"] for p in prod_analysis["product_stats"]]

    # Chart 2: Cost Breakdown
    cost_labels = ["Pembelian Bahan Baku", "Maintenance Mesin", "Operasional & Produksi"]
    cost_values = [
        fin_analysis["breakdown"]["material"],
        fin_analysis["breakdown"]["maintenance"],
        fin_analysis["breakdown"]["production"],
    ]

    # Chart 3: Category Revenue Breakdown
    cat_summary = {}
    for p in prod_analysis["product_stats"]:
        cat = p.get("category", "Lainnya")
        cat_summary[cat] = cat_summary.get(cat, 0) + p["total_revenue"]
    cat_labels = list(cat_summary.keys())
    cat_values = list(cat_summary.values())

    # Chart 4: Machine Health by Line
    machines = list(machines_col.find())
    line_scores = {}
    line_counts = {}
    for m in machines:
        l_type = m.get("type", "General")
        line_scores[l_type] = line_scores.get(l_type, 0) + m.get("health_score", 100)
        line_counts[l_type] = line_counts.get(l_type, 0) + 1
    line_labels = list(line_scores.keys())
    line_avg_health = [round(line_scores[k] / line_counts[k], 1) for k in line_labels]

    return render_template(
        "manager_charts.html",
        active_page="charts",
        fin=fin_analysis,
        prod=prod_analysis,
        company_cash=company_cash,
        base_capital_cash=base_capital_cash,
        chart_data={
            "prod_labels": prod_labels,
            "prod_revenues": prod_revenues,
            "prod_quantities": prod_quantities,
            "cost_labels": cost_labels,
            "cost_values": cost_values,
            "cat_labels": cat_labels,
            "cat_values": cat_values,
            "line_labels": line_labels,
            "line_avg_health": line_avg_health,
        },
    )


@app.route("/manager/update_base_capital", methods=["POST"])
def update_base_capital():
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    try:
        new_base = float(request.form.get("base_capital_cash", 3870233000))
        company_settings_col.update_one(
            {"key": "base_capital_cash"},
            {"$set": {"base_capital_cash": new_base}},
            upsert=True
        )
        flash(f"Modal Kas Awal berhasil diperbarui menjadi Rp {new_base:,.0f} dan seluruh saldo kas disinkronkan kembali.", "success")
    except Exception as e:
        flash(f"Gagal memperbarui modal kas awal: {e}", "danger")
    return redirect(url_for("manager_financial_activity"))


@app.route("/manager/procurement_approval")
def manager_procurement_approval():
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    procurements = list(procurement_col.find().sort("_id", -1))
    material_recommendations = ai_helper.ai_recommend_raw_material_needs()
    return render_template(
        "manager_procurements.html",
        active_page="procurements",
        procurements=procurements,
        material_recommendations=material_recommendations,
    )


@app.route("/manager/maintenance_approval")
def manager_maintenance_approval():
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    maintenances = list(maintenance_col.find().sort("_id", -1))
    return render_template(
        "manager_maintenances.html",
        active_page="maintenances",
        maintenances=maintenances,
    )


@app.route("/manager/approve_procurement/<request_id>", methods=["POST"])
def approve_procurement(request_id):
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    pr = procurement_col.find_one({"request_id": request_id})
    if pr and pr["status"] != "Approved":
        procurement_col.update_one({"request_id": request_id}, {"$set": {"status": "Approved"}})
        inventory_col.update_one(
            {"material_id": pr["material_id"]},
            {"$inc": {"stock_kg": pr["quantity_kg"]}},
        )
        finance_col.insert_one({
            "type": "Expense",
            "description": f"Pembelian Bahan Baku {pr['material_name']} ({pr['quantity_kg']} kg)",
            "amount": pr["estimated_cost"],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        flash("Pengadaan bahan baku disetujui & stok bertambah.", "success")
    return redirect(url_for("manager_procurement_approval"))


@app.route("/manager/approve_maintenance/<request_id>", methods=["POST"])
def approve_maintenance(request_id):
    if session.get("role") != "manager":
        return redirect(url_for("login"))
    maint = maintenance_col.find_one({"request_id": request_id})
    if maint and maint["status"] != "Approved":
        maintenance_col.update_one({"request_id": request_id}, {"$set": {"status": "Approved"}})
        machines_col.update_one(
            {"machine_id": maint["machine_id"]},
            {
                "$set": {
                    "status": "Available",
                    "health_score": 100,
                    "total_completed_wos": 0,
                    "total_units_produced": 0,
                    "last_sensor": {"temperature_c": 42.0, "vibration_mm_s": 1.2, "current_amp": 11.5},
                    "last_maintenance_date": datetime.now().strftime("%Y-%m-%d"),
                }
            },
        )
        finance_col.insert_one({
            "type": "Expense",
            "description": f"Biaya Maintenance Mesin {maint['machine_id']} ({maint['maintenance_type']})",
            "amount": maint["estimated_cost"],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        flash("Maintenance disetujui.", "success")
    return redirect(url_for("manager_maintenance_approval"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)