"""Controlled library comparison. Install raghealth==0.5.5 and ragfresh==0.1.0 separately.

No SDK calls, vector databases or model calls occur in this comparison.
The exact-set baseline is intentionally a few lines: it is an alternative to Wraith.
"""

import json
from datetime import datetime, timezone
from raghealth import scan, Chunk, SourceDoc
from ragfresh.check import check
from ragfresh.ledger import Ledger
from ragfresh.hashing import content_hash
from ragfresh.sources.base import SourceDoc as FreshDoc

stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)


class HealthStore:
    name = "controlled-store"

    def __init__(self, ids):
        self.ids = ids

    def fetch_chunks(self, **kwargs):
        return [Chunk(id=i, source_path="policy", embedded_at=stamp) for i in self.ids]


class HealthSource:
    name = "controlled-source"

    def fetch_documents(self):
        return [
            SourceDoc(
                path="policy",
                last_modified=stamp,
                metadata={"expected_chunk_ids": ["policy#0", "policy#1", "policy#2"]},
            )
        ]


class FreshSource:
    def list_docs(self):
        return iter([FreshDoc("policy", "same content", "policy")])


class FreshStore:
    def __init__(self, ids):
        self.ids = ids

    def list_indexed_ids(self):
        return set(self.ids)


results = []
for name, ids in [
    ("complete", ["policy#0", "policy#1", "policy#2"]),
    ("partial", ["policy#0", "policy#2"]),
    ("wrong-same-count", ["policy#0", "policy#1", "policy#9"]),
    ("missing", []),
]:
    h = scan(HealthStore(ids), HealthSource(), include_embeddings=False)
    with Ledger(":memory:") as ledger:
        ledger.record("policy", "policy", content_hash("same content"))
        f = check(
            FreshSource(),
            FreshStore(ids),
            ledger,
            chunk_id_to_doc_id=lambda x: x.split("#")[0],
        )
    expected = {"policy#0", "policy#1", "policy#2"}
    results.append(
        {
            "case": name,
            "raghealth_findings": h.total_findings,
            "raghealth_coverage": h.results[2].stats,
            "ragfresh": json.loads(f.to_json()),
            "exact_set_comparison": {
                "missing": sorted(expected - set(ids)),
                "unexpected": sorted(set(ids) - expected),
            },
        }
    )
print(json.dumps(results, indent=2))
