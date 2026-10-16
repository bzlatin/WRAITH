"""Optional pre-write manifest transformation for an uncached LlamaIndex rebuild.

Use a new candidate collection with one writer. Attach this as the last transform,
after parsing and embedding. The caller supplies authoritative source revisions;
no expectations are derived from the vector store or returned pipeline output.
"""

import json
from pathlib import Path

from llama_index.core.schema import TransformComponent

from qdrant_export import identifier


class ManifestCapture(TransformComponent):
    destination: str
    scope: str
    generation: str
    tenant: str
    revisions: dict[str, str]

    def __call__(self, nodes, **kwargs):
        for value in (self.scope, self.generation, self.tenant):
            identifier(value)
        chunks = {identifier(doc): [] for doc in self.revisions}
        seen = set()
        for revision in self.revisions.values():
            identifier(revision)
        for node in nodes:
            doc = node.ref_doc_id
            if doc not in chunks or node.id_ in seen:
                raise ValueError("Unknown document or duplicate chunk identity")
            identifier(node.id_)
            seen.add(node.id_)
            chunks[doc].append(node.id_)
            metadata = {
                "tenant": self.tenant,
                "document_id": doc,
                "chunk_id": node.id_,
                "revision": self.revisions[doc],
            }
            node.metadata.update(metadata)
            for key in metadata:
                if key not in node.excluded_embed_metadata_keys:
                    node.excluded_embed_metadata_keys.append(key)
                if key not in node.excluded_llm_metadata_keys:
                    node.excluded_llm_metadata_keys.append(key)
        header = {
            "schema_version": 1,
            "kind": "manifest",
            "scope": self.scope,
            "generation": self.generation,
            "stable": True,
            "complete": True,
            "record_count": len(chunks),
        }
        rows = [
            {
                "tenant": self.tenant,
                "document_id": doc,
                "state": "present",
                "settled": True,
                "revision": self.revisions[doc],
                "expected_chunks": sorted(chunks[doc]),
                "job_id": self.generation,
            }
            for doc in sorted(chunks)
        ]
        lines = [json.dumps(row) + "\n" for row in [header, *rows]]
        if any(len(line.encode()) > 1024 * 1024 for line in lines):
            raise ValueError("Manifest row exceeds 1 MiB")
        # A failure, including an existing evidence path, stops before the store writes.
        with Path(self.destination).open("x", encoding="utf-8") as stream:
            stream.writelines(lines)
        return nodes


def attach_capture(pipeline, capture):
    """Reject cache/docstore modes that can skip the side-effecting transform.

    No monkeypatching or framework internals. The caller still owns publication,
    source snapshots, evidence paths and the post-write visibility barrier.
    """
    if not pipeline.disable_cache or pipeline.docstore is not None:
        raise ValueError("Manifest capture requires disable_cache=True and no docstore")
    pipeline.transformations.append(capture)
