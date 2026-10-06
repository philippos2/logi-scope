"""Pinned CPU embedding adapter. Queries and passages have distinct prefixes."""

import threading

import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-base"
MODEL_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
DIMENSIONS = 768
EMBEDDING_ID = f"{MODEL_NAME}@{MODEL_REVISION}:query-passage:l2:512"


class E5Embedder:
    def __init__(self):
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(4)
        self.model = SentenceTransformer(
            MODEL_NAME, revision=MODEL_REVISION, device="cpu", trust_remote_code=False,
        )
        self.model.max_seq_length = 512
        if self.model.get_embedding_dimension() != DIMENSIONS:
            raise ValueError("embedding_dimension_mismatch")
        self.lock = threading.Lock()

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        prefix = "query: " if query else "passage: "
        inputs = [prefix + text for text in texts]
        with self.lock:
            lengths = self.model.tokenizer(inputs, truncation=False, padding=False)["input_ids"]
            if any(len(tokens) > self.model.max_seq_length for tokens in lengths):
                raise ValueError("embedding_input_too_long")
            vectors = self.model.encode(
                inputs, normalize_embeddings=True, batch_size=8, show_progress_bar=False,
            )
        if vectors.shape != (len(texts), DIMENSIONS) or not np.isfinite(vectors).all():
            raise ValueError("invalid_embedding_vectors")
        return vectors.tolist()
