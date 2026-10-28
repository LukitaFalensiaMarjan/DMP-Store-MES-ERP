import os, sys
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
from config import orders_col

orders_col.update_one({'order_id': 'ORD-0008'}, {'$set': {'order_id': 'ORD-0006'}})
orders_col.update_one({'order_id': 'ORD-0009'}, {'$set': {'order_id': 'ORD-0007'}})
orders_col.update_one({'order_id': 'ORD-0010'}, {'$set': {'order_id': 'ORD-0008'}})
print([(o['order_id'], o['status']) for o in orders_col.find()])
