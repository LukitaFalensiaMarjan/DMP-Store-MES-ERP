import joblib
import pandas as pd
from datetime import datetime, timedelta
from config import (
    products_col,
    inventory_col,
    machines_col,
    work_orders_col,
    orders_col,
    finance_col,
    company_settings_col,
)

model_eta = joblib.load("ai_models/model_eta.pkl")
model_feasibility = joblib.load("ai_models/model_feasibility.pkl")


def check_material_availability(product_id, order_qty):
    product = products_col.find_one({"product_id": product_id})
    if not product:
        return 0, False, [], []

    bom = product.get("bom_per_pcs", {})
    coverage_list = []
    shortages = []
    requirements = []

    for mat_id, req_per_pcs in bom.items():
        total_req = round(req_per_pcs * order_qty, 2)
        mat_doc = inventory_col.find_one({"material_id": mat_id})
        current_stock = round(mat_doc["stock_kg"], 2) if mat_doc else 0.0
        in_use_stock = round(mat_doc.get("in_use_kg", 0.0), 2) if mat_doc else 0.0

        ratio = (current_stock / total_req) * 100 if total_req > 0 else 100
        coverage_list.append(min(ratio, 150))

        is_enough = current_stock >= total_req
        req_item = {
            "material_id": mat_id,
            "name": mat_doc["name"] if mat_doc else mat_id,
            "needed": total_req,
            "available": current_stock,
            "in_use": in_use_stock,
            "remaining_after": round(current_stock - total_req, 2),
            "is_enough": is_enough
        }
        requirements.append(req_item)

        if not is_enough:
            shortages.append({
                "material_id": mat_id,
                "name": mat_doc["name"] if mat_doc else mat_id,
                "needed": total_req,
                "available": current_stock,
                "deficit": round(total_req - current_stock, 2)
            })

    avg_coverage = sum(coverage_list) / len(coverage_list) if coverage_list else 100
    is_stock_ready = 1 if len(shortages) == 0 else 0
    return round(avg_coverage, 1), is_stock_ready, shortages, requirements


def recommend_machines_for_product(product_id):
    product = products_col.find_one({"product_id": product_id})
    req_type = product.get("required_line_type", "Liquid Processing") if product else "Liquid Processing"

    compatible_machines = list(machines_col.find({"type": req_type}))
    sorted_machines = sorted(
        compatible_machines,
        key=lambda m: (1 if m["status"] == "Available" else 0, m["health_score"]),
        reverse=True
    )
    best_machine = sorted_machines[0] if sorted_machines else None
    available_count = sum(1 for m in compatible_machines if m["status"] == "Available")

    return {
        "required_line_type": req_type,
        "compatible_machines": sorted_machines,
        "best_machine": best_machine,
        "available_count": available_count,
        "total_line_units": len(compatible_machines)
    }


def predict_order_eta(product_id, order_qty):
    product = products_col.find_one({"product_id": product_id})
    speed = product["base_speed_pcs_per_hour"] if product else 200
    req_type = product.get("required_line_type", "Liquid Processing") if product else "Liquid Processing"

    line_machines = list(machines_col.find({"type": req_type}))
    available_units = sum(1 for m in line_machines if m["status"] == "Available")
    avg_health = sum(m["health_score"] for m in line_machines) / len(line_machines) if line_machines else 85

    active_queues = work_orders_col.count_documents({"status": {"$in": ["Scheduled", "In Progress"]}})
    _, stock_ready, _, _ = check_material_availability(product_id, order_qty)

    effective_queues = max(0, active_queues - available_units)

    input_df = pd.DataFrame([{
        "order_qty": order_qty,
        "machine_speed": speed,
        "active_queues": effective_queues,
        "stock_ready": stock_ready,
        "avg_machine_health": avg_health
    }])

    est_days = float(model_eta.predict(input_df)[0])
    est_days = max(1.0, round(est_days, 1))
    min_target_date = (datetime.now() + timedelta(days=int(est_days + 0.9))).strftime("%Y-%m-%d")

    return {
        "estimated_days": est_days,
        "min_target_date": min_target_date,
        "stock_ready": bool(stock_ready),
        "active_queues": active_queues,
        "available_units": available_units,
        "required_line_type": req_type,
        "avg_machine_health": round(avg_health, 1)
    }


def evaluate_order_feasibility(product_id, order_qty, user_target_date_str):
    eta_info = predict_order_eta(product_id, order_qty)
    avg_coverage, _, shortages, requirements = check_material_availability(product_id, order_qty)
    machine_rec = recommend_machines_for_product(product_id)

    try:
        target_dt = datetime.strptime(user_target_date_str, "%Y-%m-%d")
        days_available = (target_dt - datetime.now()).days + 1
    except ValueError:
        days_available = eta_info["estimated_days"]

    days_margin = days_available - eta_info["estimated_days"]

    input_df = pd.DataFrame([{
        "stock_coverage_pct": avg_coverage,
        "machine_health": eta_info["avg_machine_health"],
        "days_margin": days_margin
    }])

    pred = int(model_feasibility.predict(input_df)[0])
    prob = float(model_feasibility.predict_proba(input_df)[0][1]) * 100

    reasons = []
    if shortages:
        deficit_names = ", ".join([f"{s['name']} (-{s['deficit']} kg)" for s in shortages])
        reasons.append(f"Defisit bahan baku: {deficit_names}.")
    if machine_rec["available_count"] == 0:
        reasons.append(f"Semua unit mesin di lini {machine_rec['required_line_type']} sedang sibuk.")
    else:
        reasons.append(f"Tersedia {machine_rec['available_count']}/20 unit mesin {machine_rec['required_line_type']}.")

    if days_margin < 0:
        reasons.append(f"Target tanggal terlalu mepet (estimasi ~{eta_info['estimated_days']} hari).")
    if not shortages and days_margin >= 0 and machine_rec["available_count"] > 0:
        reasons.append("Stok bahan baku aman & jadwal produksi memungkinkan.")

    is_feasible = bool(pred == 1 and len(shortages) == 0 and machine_rec["available_count"] > 0)

    return {
        "is_feasible": is_feasible,
        "confidence_score": round(prob, 1),
        "recommendation": "Direkomendasikan Terima" if is_feasible else "Berisiko / Restock Bahan Baku Dahulu",
        "reasons": reasons,
        "shortages": shortages,
        "requirements": requirements,
        "estimated_days": eta_info["estimated_days"],
        "required_line_type": machine_rec["required_line_type"],
        "best_machine": machine_rec["best_machine"],
        "compatible_machines": machine_rec["compatible_machines"]
    }


def analyze_sensor_condition(temp_c, vibration_mm_s, current_amp, base_health=100):
    penalty = 0
    warnings = []

    if temp_c > 65:
        penalty += 25
        warnings.append("Suhu mesin terlalu panas (Overheating > 65°C).")
    elif temp_c > 55:
        penalty += 10
        warnings.append("Suhu mesin mulai meningkat (> 55°C).")

    if vibration_mm_s > 4.5:
        penalty += 30
        warnings.append("Getaran mesin kritis (> 4.5 mm/s), cek bearing atau poros.")
    elif vibration_mm_s > 2.8:
        penalty += 12
        warnings.append("Getaran mesin di atas normal (> 2.8 mm/s).")

    if current_amp > 20:
        penalty += 20
        warnings.append("Arus listrik berlebih (Overcurrent > 20A).")

    new_health = max(20, min(100, round(base_health - penalty)))
    need_maintenance = new_health < 75 or len(warnings) >= 2 or base_health < 75

    return {
        "penalty": penalty,
        "calculated_health": new_health,
        "need_maintenance": need_maintenance,
        "warnings": warnings if warnings else ["Kondisi sensor normal dan stabil."]
    }


def ai_recommend_maintenance_priority():
    machines = list(machines_col.find())
    scored_machines = []

    for m in machines:
        assigned_wo = work_orders_col.count_documents({"machine_id": m["machine_id"], "status": {"$in": ["Scheduled", "In Progress"]}})
        health = m["health_score"]
        sensor = m.get("last_sensor", {"temperature_c": 45.0, "vibration_mm_s": 1.5, "current_amp": 12.0})
        
        urgency_score = round((100 - health) * 1.5 + (assigned_wo * 12), 1)

        reasons = []
        actions = []

        if health < 65:
            reasons.append(f"Skor kesehatan mesin kritis ({health}%), mengindikasikan keausan komponen mekanis berat.")
            actions.append("Lakukan pembongkaran minor (overhaul), periksa pelumasan gear box, dan kalibrasi sensor.")
        elif health < 82:
            reasons.append(f"Skor kesehatan mulai menurun ({health}%) akibat tingginya beban kerja.")
            actions.append("Lakukan pembersihan filter, pengecekan klem kelistrikan, dan uji getaran lanjutan.")
        else:
            reasons.append("Kondisi mesin terpantau stabil berdasarkan data sensor terakhir.")
            actions.append("Lakukan pemeliharaan preventif rutin sesuai jadwal.")

        if sensor["temperature_c"] > 55:
            reasons.append(f"Suhu operasional tinggi ({sensor['temperature_c']}°C).")
            actions.append("Periksa sistem pendingin / sirkulasi cairan pendingin.")
        if sensor["vibration_mm_s"] > 2.8:
            reasons.append(f"Getaran di atas normal ({sensor['vibration_mm_s']} mm/s).")
            actions.append("Kencangkan baut mounting dan periksa kelurusan poros.")

        if health < 65 or urgency_score > 45 or sensor["temperature_c"] > 55:
            status_urgency = "Darurat / Segera"
        elif health < 82:
            status_urgency = "Perlu Perhatian"
        else:
            status_urgency = "Normal / Aman"

        scored_machines.append({
            "machine_id": m["machine_id"],
            "name": m["name"],
            "type": m["type"],
            "status": m["status"],
            "health_score": health,
            "active_load": assigned_wo,
            "urgency_score": urgency_score,
            "status_urgency": status_urgency,
            "sensor": sensor,
            "reasons": reasons,
            "actions": actions
        })

    return sorted(scored_machines, key=lambda x: x["urgency_score"], reverse=True)


def ai_recommend_raw_material_needs():
    active_orders = list(orders_col.find({"status": {"$in": ["Pending", "Approved"]}}))
    pending_demand = {}

    for o in active_orders:
        prod = products_col.find_one({"product_id": o["product_id"]})
        if prod:
            for mat_id, req_per_pcs in prod.get("bom_per_pcs", {}).items():
                pending_demand[mat_id] = pending_demand.get(mat_id, 0.0) + (req_per_pcs * o["quantity"])

    recommendations = []
    for mat in inventory_col.find():
        mat_id = mat["material_id"]
        current_stock = round(mat["stock_kg"], 2)
        in_use_kg = round(mat.get("in_use_kg", 0.0), 2)
        predicted_need = round(pending_demand.get(mat_id, mat["min_threshold"] * 1.2), 2)

        if current_stock < predicted_need or current_stock <= mat["min_threshold"]:
            status = "URGENT RESTOCK (Stok Kritis / Defisit Order)"
            priority_rank = 1
        elif current_stock <= (mat["min_threshold"] * 1.5):
            status = "Perlu Diprioritaskan Restock"
            priority_rank = 2
        else:
            status = "Stok Tersedia Aman"
            priority_rank = 3

        recommendations.append({
            "material_id": mat_id,
            "name": mat["name"],
            "current_stock": current_stock,
            "in_use_kg": in_use_kg,
            "min_threshold": mat["min_threshold"],
            "predicted_need": predicted_need,
            "recommended_buy_kg": max(500, round(predicted_need - current_stock + mat["min_threshold"], 0)) if priority_rank < 3 else 0,
            "status": status,
            "priority_rank": priority_rank
        })

    return sorted(recommendations, key=lambda x: (x["priority_rank"], x["current_stock"]))


def ai_analyze_financial_health():
    records = list(finance_col.find())
    total_inc = sum(r["amount"] for r in records if r["type"] == "Income")
    exp_records = [r for r in records if r["type"] == "Expense"]
    total_exp = sum(r["amount"] for r in exp_records)
    profit = total_inc - total_exp

    maint_exp = sum(r["amount"] for r in exp_records if "Maintenance" in r.get("description", ""))
    material_exp = sum(r["amount"] for r in exp_records if "Bahan Baku" in r.get("description", ""))
    prod_exp = total_exp - maint_exp - material_exp

    setting = company_settings_col.find_one({"key": "base_capital_cash"})
    base_capital = setting.get("base_capital_cash", 3870233000) if setting else 3870233000
    company_cash = base_capital + total_inc - total_exp

    insights = []
    insights.append(f"Saldo kas likuid perusahaan saat ini: Rp {format(int(company_cash), ',d')} (Modal Kas Awal Rp {format(int(base_capital), ',d')} tersinkronisasi dengan total omset masuk Rp {format(int(total_inc), ',d')} dan pengeluaran Rp {format(int(total_exp), ',d')}).")
    if total_inc == 0:
        insights.append("Belum ada pendapatan masuk dari pesanan yang dikirim.")
    elif profit > 0:
        insights.append(f"Keuangan operasional sehat surplus laba bersih Rp {format(int(profit), ',d')} (Margin {round((profit/total_inc)*100, 1)}%). Arus kas positif.")
    else:
        insights.append("Pengeluaran sementara lebih besar dari pendapatan. Prioritaskan pengiriman order.")

    return {
        "total_income": total_inc,
        "total_expense": total_exp,
        "net_profit": profit,
        "base_capital": base_capital,
        "company_cash": company_cash,
        "breakdown": {"maintenance": maint_exp, "material": material_exp, "production": prod_exp},
        "ai_insights": insights
    }


def ai_analyze_product_performance():
    products = list(products_col.find())
    orders = list(orders_col.find())

    sales_summary = {}
    for p in products:
        sales_summary[p["product_id"]] = {
            "product_id": p["product_id"],
            "name": p["name"],
            "category": p["category"],
            "total_qty": 0,
            "total_revenue": 0,
            "order_count": 0
        }

    for o in orders:
        pid = o["product_id"]
        if pid in sales_summary:
            sales_summary[pid]["total_qty"] += o["quantity"]
            sales_summary[pid]["total_revenue"] += o["total_price"]
            sales_summary[pid]["order_count"] += 1

    sorted_products = sorted(sales_summary.values(), key=lambda x: x["total_revenue"], reverse=True)

    recommendations = []
    if sorted_products:
        top_prod = sorted_products[0]
        low_prod = sorted_products[-1]
        recommendations.append(f"Produk Prioritas Utama: {top_prod['name']} dengan omzet Rp {format(int(top_prod['total_revenue']), ',d')}.")
        if low_prod["total_revenue"] == 0:
            recommendations.append(f"Produk Kurang Berkembang: {low_prod['name']} belum memiliki order aktif.")

    return {
        "product_stats": sorted_products,
        "recommendations": recommendations
    }


def get_chatbot_reply(user_message, username=None):
    msg = user_message.strip().lower()

    # 1. Salam / Greeting
    greetings = ["halo", "hai", "hi", "hey", "pagi", "siang", "sore", "malam", "assalam"]
    if any(msg.startswith(g) or f" {g}" in msg for g in greetings) and len(msg.split()) <= 4:
        return (
            "Halo! Saya Asisten AI DMP Store. Saya dapat membantu Anda mengecek status & target pesanan Anda, "
            "ketersediaan stok bahan baku, harga produk, serta minimal order (MOQ). Ada yang bisa saya bantu?"
        )

    # 2. Ucapan Terima Kasih
    thanks = ["terima kasih", "makasih", "terimakasih", "thanks", "thank you"]
    if any(t in msg for t in thanks):
        return "Sama-sama! Senang dapat membantu Anda. Jika ada pertanyaan lain seputar produksi, silakan tanyakan."

    # 3. Pertanyaan seputar Status / Kapan Selesai Order / Pesanan User
    is_asking_order = (
        ("kapan" in msg and any(k in msg for k in ["selesai", "beres", "jadi", "order", "pesanan", "barang", "kirim", "dikirim"])) or
        ("status" in msg and any(k in msg for k in ["order", "pesanan", "orderan", "saya", "barang"])) or
        ("cek" in msg and any(k in msg for k in ["order", "pesanan", "orderan"])) or
        ("pesanan saya" in msg or "orderan saya" in msg or "order saya" in msg)
    )

    if is_asking_order:
        if not username:
            return "Untuk mengecek status pesanan, pastikan Anda telah login ke akun Anda."

        user_orders = list(orders_col.find({"username": username}).sort("_id", -1).limit(3))
        if not user_orders:
            return (
                "Saat ini belum ada riwayat order aktif atas akun Anda. "
                "Anda dapat memilih produk dari katalog dan melakukan checkout untuk membuat Work Order baru."
            )

        latest = user_orders[0]
        status = latest.get("status", "Pending")
        p_name = latest.get("product_name", "Produk")
        qty = latest.get("quantity", 0)
        target = latest.get("target_date", "-")
        oid = latest.get("order_id", "-")

        status_desc = {
            "Pending": "sedang menunggu verifikasi kelayakan oleh Supervisi Produksi",
            "Approved": "telah disetujui Supervisi dan dalam antrean penjadwalan mesin",
            "In Production": "sedang dalam proses produksi aktif di pabrik",
            "Completed": "telah selesai diproduksi dan siap dikirim",
            "Shipped": "telah selesai dan dikirim ke alamat Anda",
            "Rejected": "ditolak oleh Supervisi (silakan cek catatan supervisi)"
        }.get(status, f"berstatus {status}")

        reply = (
            f"[Status Order] Pesanan terakhir Anda ({oid} - {p_name}, {qty:,.0f} pcs) saat ini {status_desc}. "
            f"Target selesai: {target}."
        )

        if latest.get("supervisor_note"):
            reply += f" Catatan Supervisi: \"{latest.get('supervisor_note')}\"."

        return reply

    # 4. Pertanyaan seputar Stok / Ketersediaan Bahan Baku
    is_asking_stock = any(k in msg for k in ["stok", "stock", "bahan", "bahan baku", "ketersediaan", "ready", "sedia"])
    if is_asking_stock:
        all_materials = list(inventory_col.find())
        matched_mat = None
        for m in all_materials:
            m_name_lower = m["name"].lower()
            keywords = [w for w in m_name_lower.replace("&", " ").replace("-", " ").split() if len(w) > 3]
            if any(kw in msg for kw in keywords) or m_name_lower in msg or m["material_id"].lower() in msg:
                matched_mat = m
                break

        if matched_mat:
            stk = matched_mat.get("stock_kg", 0.0)
            in_use = matched_mat.get("in_use_kg", 0.0)
            threshold = matched_mat.get("min_threshold", 0)
            cond = "Aman & Siap Digunakan" if stk >= threshold else "Menipis / Perlu Pengadaan"
            return (
                f"[Stok Bahan] Ketersediaan {matched_mat['name']} saat ini: {stk:,.1f} kg "
                f"(Sedang dipakai produksi: {in_use:,.1f} kg). Status: {cond}."
            )

        all_prods = list(products_col.find())
        matched_prod = None
        for p in all_prods:
            p_name_lower = p["name"].lower()
            keywords = [w for w in p_name_lower.split() if len(w) > 3]
            if any(kw in msg for kw in keywords) or p["product_id"].lower() in msg:
                matched_prod = p
                break

        if matched_prod:
            return (
                f"[Info Produk] Produk {matched_prod['name']} diproduksi secara Make-to-Order (manufaktur sesuai pesanan) "
                f"dengan MOQ {matched_prod['min_order']:,} pcs dan harga Rp {matched_prod['price_per_pcs']:,}/pcs. "
                f"Ketersediaan bahan baku formula produk ini siap diproses di lini pabrik."
            )

        total_mats = len(all_materials)
        safe_mats = sum(1 for m in all_materials if m.get("stock_kg", 0) >= m.get("min_threshold", 0))
        return (
            f"[Gudang Bahan] Gudang DMP Store saat ini memiliki {total_mats} varian bahan baku aktif ({safe_mats} bahan dalam stok aman). "
            f"Anda dapat menanyakan stok bahan spesifik seperti Niacinamide, Charcoal, Aloe Vera, Clay, dll."
        )

    # 5. Pertanyaan seputar Harga Produk / MOQ / Katalog
    is_asking_product = any(k in msg for k in ["harga", "biaya", "moq", "minimal", "katalog", "daftar produk", "produk apa", "pcs"])
    if is_asking_product:
        all_prods = list(products_col.find())
        for p in all_prods:
            p_name_lower = p["name"].lower()
            keywords = [w for w in p_name_lower.split() if len(w) > 3]
            if any(kw in msg for kw in keywords) or p["product_id"].lower() in msg:
                return (
                    f"[Katalog] {p['name']} ({p.get('category', 'Skincare')}): "
                    f"Harga Rp {p['price_per_pcs']:,}/pcs dengan Minimal Order (MOQ) {p['min_order']:,} pcs. "
                    f"Kapasitas lini mesin: ~{p.get('base_speed_pcs_per_hour', 200)} pcs/jam."
                )

        if any(k in msg for k in ["moq", "minimal"]):
            return (
                "[Info MOQ] Minimal Order (MOQ) di DMP Store bervariasi sesuai jenis produk: "
                "Sunscreen & Serum (MOQ 300 pcs), Facial Wash & Body Care (MOQ 400-500 pcs), dan Sabun Batang (MOQ 1.000 pcs)."
            )

        if any(k in msg for k in ["harga", "biaya", "katalog", "produk"]):
            return (
                "[Katalog DMP Store] DMP Store memproduksi Skincare Pria & Wanita, Sabun Batang, Body Care, Sunscreen, dan Serum. "
                "Harga berkisar antara Rp 28.000 - Rp 75.000 per pcs. Silakan lihat katalog produk di dashboard untuk detail lengkap."
            )

    # 6. Fallback jika tidak dapat dijawab
    return "Pesan Anda telah diteruskan ke Supervisi Produksi."