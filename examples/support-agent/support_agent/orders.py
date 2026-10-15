"""Synthetic backend; the caller identity comes from the application boundary."""

ORDERS = {
    "A100": {"customer": "alice", "status": "shipped"},
    "B200": {"customer": "bob", "status": "processing"},
}


def lookup(order_id, customer):
    order = ORDERS.get(order_id)
    if order is None or order["customer"] != customer:
        return None
    return {"id": order_id, "status": order["status"]}
