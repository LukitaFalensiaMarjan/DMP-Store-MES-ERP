from pymongo import MongoClient

db = MongoClient('localhost', 27017)['dmp_store_db']
res = db.customer_orders.update_many(
    {'order_id': {'$in': ['ORD-0006', 'ORD-0007', 'ORD-0008']}},
    {'$set': {'status': 'Pending Manager Approval', 'approval_status': None}}
)
print('Updated count:', res.modified_count)
for o in db.customer_orders.find({'order_id': {'$in': ['ORD-0006', 'ORD-0007', 'ORD-0008']}}):
    print(o['order_id'], '|', o['customer_name'], '|', o['product_name'], '|', o['status'])
