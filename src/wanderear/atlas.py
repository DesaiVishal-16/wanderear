"""Optional MongoDB Atlas store + Vector Search.

The local JSON-lines store remains the source of truth; Atlas is a mirror used
by the hosted gallery and for cross-device semantic search. Import is lazy so
the app never depends on pymongo.
"""

from __future__ import annotations

from .embeddings import cosine


class AtlasStore:
    def __init__(self, uri: str, database: str = "wanderear",
                 collection: str = "postcards",
                 index_name: str = "wanderear_vector") -> None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("atlas needs pymongo (pip install 'wanderear[cloud]')") from exc
        self._client = MongoClient(uri)
        self._col = self._client[database][collection]
        self._index_name = index_name

    def upsert(self, postcard: dict) -> None:
        self._col.replace_one({"id": postcard["id"]}, postcard, upsert=True)

    def upsert_many(self, postcards: list[dict]) -> int:
        from pymongo import ReplaceOne

        operations = [
            ReplaceOne({"id": c["id"]}, c, upsert=True) for c in postcards if c.get("id")
        ]
        if not operations:
            return 0
        result = self._col.bulk_write(operations, ordered=False)
        return result.upserted_count + result.modified_count

    def similar(self, query_embedding: list[float], limit: int = 5) -> list[dict]:
        """Atlas Vector Search if the index exists, otherwise client-side cosine."""
        try:
            cursor = self._col.aggregate([
                {
                    "$vectorSearch": {
                        "index": self._index_name,
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": max(100, limit * 20),
                        "limit": limit,
                    }
                },
                {"$set": {"score": {"$meta": "vectorSearchScore"}}},
            ])
            return [{k: v for k, v in doc.items() if k != "_id"} for doc in cursor]
        except Exception:
            return self._fallback_similar(query_embedding, limit)

    def _fallback_similar(self, query_embedding: list[float], limit: int) -> list[dict]:
        scored = []
        for doc in self._col.find({"embedding": {"$exists": True}}):
            doc.pop("_id", None)
            scored.append({**doc, "score": cosine(query_embedding, doc.get("embedding") or [])})
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:limit]