from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["dmp_store_db"]

# Inisialisasi koleksi MongoDB
users_col = db["users"]
products_col = db["products"]
inventory_col = db["raw_materials"]
machines_col = db["machines_assets"]
orders_col = db["customer_orders"]
work_orders_col = db["work_orders"]
maintenance_col = db["maintenance_logs"]
finance_col = db["financial_reports"]
procurement_col = db["procurement_requests"]
chats_col = db["chats"]
company_settings_col = db["company_settings"]