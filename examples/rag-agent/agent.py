#!/usr/bin/env python3
"""Local support RAG fixture: real corpus ranking, policy/ACL filters, extractive answers.

No model, keys, third-party packages, or scenario-ID dispatch. --ask also works
without Wraith. Mutations are isolated implementation defects for the pilot.
"""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import sys

CORPUS = Path(__file__).with_name("corpus.json")
STOP = {"a", "an", "the", "is", "are", "of", "to", "for", "my", "i", "can", "how", "what", "do", "does", "it", "and", "in", "me", "about"}
SYNONYMS = {"returns": "refund", "return": "refund", "refunds": "refund", "cancellation": "cancel", "cancelling": "cancel", "invoices": "invoice", "exports": "export", "passwords": "password"}
VARIANTS = ["baseline", "benign-wording", "benign-order", "benign-ranking", "stale-policy", "missing-acl", "wrong-route", "missing-citation"]


def tokens(text):
    return [SYNONYMS.get(word, word) for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP]


def search_documents(query, audience, variant):
    documents = json.loads(CORPUS.read_text(encoding="utf-8"))
    if variant == "benign-order":
        documents.reverse()
    available = [doc for doc in documents
                 if (variant == "stale-policy" or doc["status"] == "current")
                 and (variant == "missing-acl" or doc["audience"] == "public" or audience == "staff")]
    query_tokens = tokens(query)
    ranked = []
    for doc in available:
        words = tokens(doc["title"] + " " + doc["text"])
        counts = Counter(words)
        # Corpus-frequency weighting; repeated terms receive diminishing weight.
        score = sum((1 + math.log(counts[word])) * (1 + math.log((len(available) + 1) /
                    (1 + sum(word in tokens(d["title"] + " " + d["text"]) for d in available))))
                    for word in set(query_tokens) if counts[word])
        if variant == "benign-ranking" and score:
            score = round(score, 4)
        if score:
            ranked.append((score, doc))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    if variant == "stale-policy" and "refund" in query_tokens:
        # A faulty 'prefer legacy' migration overrides the current-only filter.
        ranked.sort(key=lambda pair: pair[1]["status"] != "archived")
    return ranked[:1]


def answer(payload, variant="baseline"):
    query = payload["question"]
    audience = payload.get("audience", "public")
    calls, retrievals = [], []
    if "order status" in query.lower() and variant != "wrong-route":
        order_id = payload.get("order_id", "")
        calls.append({"name": "lookup_order", "arguments": {"order_id": order_id}, "success": True})
        # Fixture tool backend; unknown orders are handled explicitly.
        orders = {"A100": "shipped", "A200": "processing"}
        text = f"Order {order_id}: {orders[order_id]}." if order_id in orders else "Order not found; contact support."
    else:
        calls.append({"name": "search_documents", "arguments": {"query": query, "audience": audience}, "success": True})
        ranked = search_documents(query, audience, variant)
        if not ranked:
            calls.append({"name": "escalate_to_support", "arguments": {"reason": "no authorized evidence"}, "success": True})
            text = "I could not find authorized evidence. Please contact support."
        else:
            score, doc = ranked[0]
            retrievals.append({"source": "support_knowledge_base", "documentId": doc["id"], "score": score})
            text = doc["text"]
            if variant != "missing-citation":
                text += f" [source:{doc['id']}]"
    if variant == "benign-wording":
        text = "Here is what I found: " + text
    text = text.replace("30 days", "90 days")
    return {"output": {"text": text}, "toolCalls": calls, "retrievals": retrievals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ask")
    parser.add_argument("--audience", choices=["public", "staff"], default="public")
    parser.add_argument("--variant", choices=VARIANTS, default=os.environ.get("WRAITH_RAG_VARIANT", "baseline"))
    args = parser.parse_args()
    if args.variant not in VARIANTS:
        parser.error("unknown WRAITH_RAG_VARIANT")
    if args.ask:
        print(answer({"question": args.ask, "audience": args.audience}, args.variant)["output"]["text"])
        return
    request = json.load(sys.stdin)
    result = answer(request["input"], args.variant)
    result.update(protocolVersion=1, scenarioId=request["scenarioId"])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
