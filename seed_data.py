import os
import random
import pandas as pd
from werkzeug.security import generate_password_hash
from config import db, users_col, products_col, inventory_col, machines_col

def seed_database():
    for col in db.list_collection_names():
        db[col].drop()

    users_data = [
        {"username": "user1", "password": generate_password_hash("12345"), "role": "user", "name": "Basit Rozak", "email": "basit@client.com", "phone": "081234567890", "address": "Jl. Lembang No. 10, Bandung"},
        {"username": "supervisi1", "password": generate_password_hash("12345"), "role": "supervisi", "name": "Agam Gunata"},
        {"username": "teknisi1", "password": generate_password_hash("12345"), "role": "teknisi", "name": "Azfa Hafshiam"},
        {"username": "manager1", "password": generate_password_hash("12345"), "role": "manager", "name": "Lukita Falensia"}
    ]
    users_col.insert_many(users_data)

    # 11 Bahan Baku Manufaktur (Dilengkapi in_use_kg untuk melacak bahan yang sedang dipakai produksi aktif)
    raw_materials = [
        {"material_id": "RM01", "name": "Base Oil & Surfaktan", "stock_kg": 4500.0, "in_use_kg": 0.0, "unit_price": 25000, "min_threshold": 600},
        {"material_id": "RM02", "name": "Niacinamide Powder", "stock_kg": 1200.0, "in_use_kg": 0.0, "unit_price": 180000, "min_threshold": 200},
        {"material_id": "RM03", "name": "Charcoal Extract", "stock_kg": 1100.0, "in_use_kg": 0.0, "unit_price": 95000, "min_threshold": 150},
        {"material_id": "RM04", "name": "Aloe Vera Gel Base", "stock_kg": 3200.0, "in_use_kg": 0.0, "unit_price": 40000, "min_threshold": 450},
        {"material_id": "RM05", "name": "Fragrance & Preservatives", "stock_kg": 1500.0, "in_use_kg": 0.0, "unit_price": 120000, "min_threshold": 250},
        {"material_id": "RM06", "name": "UV Filter Complex", "stock_kg": 1500.0, "in_use_kg": 0.0, "unit_price": 210000, "min_threshold": 300},
        {"material_id": "RM07", "name": "Zinc PCA & Aluminum Actives", "stock_kg": 1000.0, "in_use_kg": 0.0, "unit_price": 150000, "min_threshold": 200},
        {"material_id": "RM08", "name": "Micellar Surfactant Solution", "stock_kg": 2800.0, "in_use_kg": 0.0, "unit_price": 35000, "min_threshold": 400},
        {"material_id": "RM09", "name": "Hyaluronic & Centella Extract", "stock_kg": 950.0, "in_use_kg": 0.0, "unit_price": 250000, "min_threshold": 150},
        {"material_id": "RM10", "name": "Refreshing Mint & Rose Water", "stock_kg": 2400.0, "in_use_kg": 0.0, "unit_price": 45000, "min_threshold": 350},
        {"material_id": "RM11", "name": "Kaolin & Bentonite Clay", "stock_kg": 2200.0, "in_use_kg": 0.0, "unit_price": 60000, "min_threshold": 300}
    ]
    inventory_col.insert_many(raw_materials)

    # 11 Produk DMP Store (Lengkap dengan required_line_type agar sinkron dengan jenis mesin)
    products = [
        {
            "product_id": "PRD01", "name": "Facial Wash Men 100ml", "category": "Skincare Pria",
            "required_line_type": "Liquid Processing",
            "price_per_pcs": 35000, "production_cost_per_pcs": 18000, "min_order": 500, "base_speed_pcs_per_hour": 250,
            "image_url": "/img/DMP_FacialWashMen.jpg.jpeg",
            "description": "Pembersih wajah aktif pria dengan ekstrak charcoal untuk kontrol minyak berlebih.",
            "bom_per_pcs": {"RM01": 0.08, "RM03": 0.015, "RM05": 0.005}
        },
        {
            "product_id": "PRD02", "name": "Soap Women 80g", "category": "Sabun Wanita",
            "required_line_type": "Solid Soap Line",
            "price_per_pcs": 28000, "production_cost_per_pcs": 14000, "min_order": 1000, "base_speed_pcs_per_hour": 400,
            "image_url": "/img/DMP_SoapWomen.jpg.jpeg",
            "description": "Sabun batang pencerah kulit wanita dengan kandungan Niacinamide murni.",
            "bom_per_pcs": {"RM01": 0.07, "RM02": 0.008, "RM05": 0.002}
        },
        {
            "product_id": "PRD03", "name": "Aloe Vera Unisex 250ml", "category": "Body Care Unisex",
            "required_line_type": "Serum & Gel Line",
            "price_per_pcs": 45000, "production_cost_per_pcs": 22000, "min_order": 500, "base_speed_pcs_per_hour": 300,
            "image_url": "/img/DMP_AloeVeraUnisex.jpg.jpeg",
            "description": "Gel penenang dan pelembap kulit unisex dengan ekstrak lidah buaya organik.",
            "bom_per_pcs": {"RM04": 0.15, "RM05": 0.01}
        },
        {
            "product_id": "PRD04", "name": "Sunscreen SPF 50+ 50ml", "category": "Sun Care",
            "required_line_type": "Emulsion & Clay Line",
            "price_per_pcs": 75000, "production_cost_per_pcs": 38000, "min_order": 300, "base_speed_pcs_per_hour": 200,
            "image_url": "/img/DMP_Sunscreen.jpg.jpeg",
            "description": "Tabir surya emulsi ringan perlindungan maksimal terhadap sinar UVA & UVB.",
            "bom_per_pcs": {"RM01": 0.05, "RM06": 0.03, "RM05": 0.005}
        },
        {
            "product_id": "PRD05", "name": "Serum Men 30ml", "category": "Skincare Pria",
            "required_line_type": "Serum & Gel Line",
            "price_per_pcs": 65000, "production_cost_per_pcs": 32000, "min_order": 300, "base_speed_pcs_per_hour": 180,
            "image_url": "/img/DMP_SerumMen.jpg.jpeg",
            "description": "Serum konsentrat khusus pria untuk mengecilkan pori dan menyamarkan noda.",
            "bom_per_pcs": {"RM02": 0.01, "RM07": 0.015, "RM05": 0.002}
        },
        {
            "product_id": "PRD06", "name": "Deodoran Unisex 50ml", "category": "Personal Care Unisex",
            "required_line_type": "Liquid Processing",
            "price_per_pcs": 32000, "production_cost_per_pcs": 15000, "min_order": 500, "base_speed_pcs_per_hour": 350,
            "image_url": "/img/DMP_Deodorant.jpg.jpeg",
            "description": "Deodoran roll-on unisex anti-perspirant bebas bau badan hingga 48 jam.",
            "bom_per_pcs": {"RM01": 0.04, "RM07": 0.01, "RM05": 0.003}
        },
        {
            "product_id": "PRD07", "name": "Gentle Micellar Water 150ml", "category": "Cleanser",
            "required_line_type": "Liquid Processing",
            "price_per_pcs": 42000, "production_cost_per_pcs": 20000, "min_order": 400, "base_speed_pcs_per_hour": 280,
            "image_url": "/img/DMP_Gentle Micellar Water.jpg.jpeg",
            "description": "Pembersih wajah & makeup tanpa bilas dengan formula lembut ramah kulit sensitif.",
            "bom_per_pcs": {"RM08": 0.12, "RM05": 0.005}
        },
        {
            "product_id": "PRD08", "name": "Hydrating Essence Toner 100ml", "category": "Toner & Essence",
            "required_line_type": "Liquid Processing",
            "price_per_pcs": 55000, "production_cost_per_pcs": 26000, "min_order": 400, "base_speed_pcs_per_hour": 250,
            "image_url": "/img/DMP_Hydrating Essence Toner).jpg.jpeg",
            "description": "Toner esens penyeimbang pH kulit dengan Hyaluronic Acid dan Centella Asiatica.",
            "bom_per_pcs": {"RM09": 0.08, "RM05": 0.004}
        },
        {
            "product_id": "PRD09", "name": "Cooling Face Mist 60ml", "category": "Face Mist",
            "required_line_type": "Liquid Processing",
            "price_per_pcs": 38000, "production_cost_per_pcs": 17000, "min_order": 500, "base_speed_pcs_per_hour": 320,
            "image_url": "/img/DMP_CoolingFaceMist.jpg.jpeg",
            "description": "Semprotan penyegar wajah instan dengan ekstrak air mawar dan cooling mint.",
            "bom_per_pcs": {"RM10": 0.06, "RM05": 0.003}
        },
        {
            "product_id": "PRD10", "name": "Eye Serum Women 15ml", "category": "Skincare Wanita",
            "required_line_type": "Serum & Gel Line",
            "price_per_pcs": 68000, "production_cost_per_pcs": 34000, "min_order": 300, "base_speed_pcs_per_hour": 200,
            "image_url": "/img/DMP_EyeSerumWomen.jpg.jpeg",
            "description": "Serum mata intensif wanita untuk menyamarkan lingkar hitam dan garis halus.",
            "bom_per_pcs": {"RM09": 0.02, "RM02": 0.005, "RM05": 0.001}
        },
        {
            "product_id": "PRD11", "name": "Clay Mask Women 100g", "category": "Skincare Wanita",
            "required_line_type": "Emulsion & Clay Line",
            "price_per_pcs": 58000, "production_cost_per_pcs": 28000, "min_order": 400, "base_speed_pcs_per_hour": 220,
            "image_url": "/img/DMP_ClayMaskWomen.jpg.jpeg",
            "description": "Masker lumpur kaolin & bentonite untuk detoksifikasi pori wajah wanita.",
            "bom_per_pcs": {"RM11": 0.09, "RM04": 0.02, "RM05": 0.004}
        }
    ]
    products_col.insert_many(products)

    # 80 Unit Mesin (20 Unit untuk setiap jenis lini produksi)
    machine_categories = [
        {"code": "LP", "name": "Liquid Mixer & Filling", "type": "Liquid Processing"},
        {"code": "SS", "name": "Soap Bar Extruder & Stamper", "type": "Solid Soap Line"},
        {"code": "SG", "name": "Serum & Gel Homogenizer", "type": "Serum & Gel Line"},
        {"code": "EC", "name": "Emulsion & Clay Reactor", "type": "Emulsion & Clay Line"}
    ]

    machines = []
    for cat in machine_categories:
        for i in range(1, 21):
            m_id = f"MCH-{cat['code']}-{i:02d}"
            m_name = f"{cat['name']} #{i:02d}"
            health = random.randint(72, 99)
            temp = round(random.uniform(38.0, 54.0), 1)
            vib = round(random.uniform(1.1, 2.7), 1)
            curr = round(random.uniform(10.5, 16.0), 1)
            machines.append({
                "machine_id": m_id,
                "name": m_name,
                "type": cat["type"],
                "status": "Available",
                "health_score": health,
                "total_completed_wos": 0,
                "total_units_produced": 0,
                "last_maintenance_date": "2026-10-01",
                "last_sensor": {"temperature_c": temp, "vibration_mm_s": vib, "current_amp": curr}
            })
    machines_col.insert_many(machines)
    print("Database berhasil diisi: 11 Produk, 11 Bahan Baku, dan 80 Unit Mesin (20 unit per jenis lini).")

def generate_ai_datasets():
    os.makedirs("ai_models", exist_ok=True)
    records_eta = []
    for _ in range(1000):
        qty = random.randint(300, 10000)
        speed = random.choice([180, 200, 220, 250, 280, 300, 320, 350, 400])
        queues = random.randint(0, 8)
        stock_ready = random.choice([0, 1])
        health = random.randint(50, 100)
        base_days = (qty / speed) / 8.0
        est_days = round(base_days + (queues * 0.4) + (0 if stock_ready == 1 else 4.0) + ((100 - health) * 0.05) + 1, 1)
        records_eta.append([qty, speed, queues, stock_ready, health, est_days])

    df_eta = pd.DataFrame(records_eta, columns=["order_qty", "machine_speed", "active_queues", "stock_ready", "avg_machine_health", "estimated_days"])
    df_eta.to_csv("ai_models/dataset_order_eta.csv", index=False)

    records_feas = []
    for _ in range(1000):
        stock_coverage_pct = random.uniform(30, 150)
        machine_health = random.uniform(40, 100)
        days_margin = random.uniform(-3, 10)
        feasible = 1 if (stock_coverage_pct >= 80 and machine_health >= 65 and days_margin >= -0.5) else 0
        records_feas.append([round(stock_coverage_pct, 1), round(machine_health, 1), round(days_margin, 1), feasible])

    df_feas = pd.DataFrame(records_feas, columns=["stock_coverage_pct", "machine_health", "days_margin", "is_feasible"])
    df_feas.to_csv("ai_models/dataset_feasibility.csv", index=False)
    print("Dataset AI berhasil diperbarui.")

if __name__ == "__main__":
    seed_database()
    generate_ai_datasets()