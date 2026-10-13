"""Support workflow with deterministic routing and extractive answers."""

from .catalog import search
from .orders import lookup


class Session:
    def __init__(self, context=None):
        self.context = context
        self.searches = 0

    def record_tool(self, name, arguments, result):
        if self.context is not None:
            self.context.tool(name, arguments, result)

    def ask(self, request):
        query = request["question"]
        audience = request.get("audience", "public")
        customer = request.get("customer", "")
        if "order status" in query.lower() or "track order" in query.lower():
            arguments = {"order_id": request.get("order_id", ""), "customer": customer}
            order = lookup(arguments["order_id"], customer)
            self.record_tool("lookup_order", arguments, order)
            if order:
                return {
                    "status": "answered",
                    "text": f"Order {order['id']}: {order['status']}.",
                    "citations": [],
                }
            return self.escalate("Order unavailable; contact support.")
        self.searches += 1
        documents = search(query, audience)
        self.record_tool(
            "search_documents",
            {"query": query, "audience": audience},
            [d["id"] for d in documents],
        )
        if not documents:
            return self.escalate("No authorized evidence; contact support.")
        document = documents[0]
        if self.context is not None:
            self.context.retrieval("support_knowledge_base", document["id"])
        return {
            "status": "answered",
            "text": document["text"],
            "citations": [document["id"]],
        }

    def escalate(self, text):
        self.record_tool("escalate_to_support", {"reason": text}, {"queued": True})
        return {"status": "escalated", "text": text, "citations": []}


def evaluate(payload, context=None):
    session = Session(context)
    requests = payload.get("requests", [payload])
    responses = [session.ask(request) for request in requests]
    return {
        "text": "\n".join(r["text"] for r in responses),
        "responses": responses,
        "searches": session.searches,
    }
