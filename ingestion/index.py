"""Store dense and sparse BGE-M3 vectors with the retrieval payload."""

from qdrant_client import models
from qdrant_client.http.exceptions import UnexpectedResponse

from core import config

DENSE = "dense"
SPARSE = "sparse"
DOCUMENT_FIELDS = {
    "document_number",
    "title",
    "source_url",
    "effective_date",
    "effective_from_term",
    "effective_until_term_exclusive",
    "applicability",
}


def encode(model, doc, source, chunks) -> list[models.PointStruct]:
    points = []
    metadata = doc.model_dump(mode="json", include=DOCUMENT_FIELDS)
    for offset in range(0, len(chunks), 16):
        batch = chunks[offset : offset + 16]
        texts = [f"{doc.title}\n{chunk.section}\n{chunk.content}" for chunk in batch]
        vectors = model.encode_corpus(
            texts,
            batch_size=16,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        for chunk, dense, lexical in zip(
            batch, vectors["dense_vecs"], vectors["lexical_weights"], strict=True
        ):
            weights = sorted(
                (int(token), float(weight)) for token, weight in lexical.items()
            )
            # Pending content can be inspected in Qdrant; the approved retrieval filter uses review_status.
            payload = {
                **metadata,
                **chunk.model_dump(mode="json"),
                "status": "indexed",
                "file_name": source.file_name,
                "source_kind": source.source_kind,
                "embedding_model": config.EMBED_MODEL,
            }
            points.append(
                models.PointStruct(
                    id=str(chunk.chunk_id),
                    payload=payload,
                    vector={
                        DENSE: [float(value) for value in dense],
                        SPARSE: models.SparseVector(
                            indices=[index for index, _ in weights],
                            values=[weight for _, weight in weights],
                        ),
                    },
                )
            )
    return points


def upsert(client, collection: str, points: list[models.PointStruct]) -> None:
    dimensions = {len(point.vector[DENSE]) for point in points}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("Expected a single nonempty dense vector dimension")
    (size,) = dimensions
    if not client.collection_exists(collection):
        try:
            client.create_collection(
                collection_name=collection,
                vectors_config={
                    DENSE: models.VectorParams(
                        size=size, distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={SPARSE: models.SparseVectorParams()},
            )
        except (UnexpectedResponse, ValueError):
            if not client.collection_exists(collection):
                raise
    params = client.get_collection(collection).config.params
    dense = params.vectors.get(DENSE) if isinstance(params.vectors, dict) else None
    sparse = (params.sparse_vectors or {}).get(SPARSE)
    if (
        not dense
        or dense.size != size
        or dense.distance != models.Distance.COSINE
        or not sparse
        or sparse.modifier == models.Modifier.IDF
    ):
        raise ValueError(
            f"Incompatible Qdrant collection {collection!r}: expected {DENSE} ({size}, cosine) and {SPARSE} (BGE-M3)"
        )
    for offset in range(0, len(points), 128):
        result = client.upsert(
            collection_name=collection, points=points[offset : offset + 128], wait=True
        )
        if result.status != models.UpdateStatus.COMPLETED:
            raise RuntimeError(f"Qdrant returned {result.status} for an upsert")
