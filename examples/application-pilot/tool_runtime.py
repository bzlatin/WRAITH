"""Observed local tool operations for the offline application pilot."""

context = None
receipts = []


def record(name, arguments, result):
    receipts.append({"name": name, "arguments": arguments, "result": result})
    if context is not None:
        context.tool(name, arguments, result)
    return result
