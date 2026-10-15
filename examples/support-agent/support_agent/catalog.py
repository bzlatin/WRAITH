"""Retrieve current documents visible to the caller."""

from collections import Counter
import json
from pathlib import Path
import re

CORPUS = Path(__file__).resolve().parents[1] / "documents.json"
ALIASES = {
    "return": "refund",
    "returns": "refund",
    "refunds": "refund",
    "deliveries": "shipping",
    "delivery": "shipping",
    "discounts": "discount",
}
STOP = {"what", "is", "the", "a", "my", "how", "can", "i", "do", "you", "for"}


def words(text):
    return [
        ALIASES.get(w, w)
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if w not in STOP
    ]


def search(query, audience):
    documents = json.loads(CORPUS.read_text(encoding="utf-8"))
    eligible = [
        d
        for d in documents
        if d["status"] == "current"
        and (d["audience"] == "public" or audience == "staff")
    ]
    ranked = []
    for document in eligible:
        counts = Counter(words(document["title"] + " " + document["text"]))
        score = sum(counts[w] for w in set(words(query)))
        if score:
            ranked.append((score, document))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [d for _, d in ranked[:1]]
