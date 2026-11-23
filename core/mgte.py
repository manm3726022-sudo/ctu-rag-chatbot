"""mGTE dense CLS embeddings and learned lexical weights for Qdrant."""


class MgteEmbedder:
    def __init__(self, model_name, use_fp16=False):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        self.torch = torch
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        dtype = torch.float16 if self.device.type == 'cuda' and use_fp16 else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForTokenClassification.from_pretrained(model_name, dtype=dtype)
        self.model.to(self.device).eval()
        self.special_ids = set(self.tokenizer.all_special_ids)

    def encode(self, texts, *, batch_size, max_length, return_dense, return_sparse, return_colbert_vecs):
        """Use the dense/sparse result contract shared with the BGE-M3 adapter."""
        if not (return_dense and return_sparse) or return_colbert_vecs:
            raise ValueError('mGTE requires dense and sparse output')
        dense_vecs, lexical_weights = [], []
        with self.torch.inference_mode():
            for offset in range(0, len(texts), batch_size):
                inputs = self.tokenizer(
                    texts[offset:offset + batch_size], padding=True, truncation=True,
                    max_length=max_length, return_tensors='pt',
                ).to(self.device)
                output = self.model(**inputs, output_hidden_states=True)
                dense = self.torch.nn.functional.normalize(output.hidden_states[-1][:, 0].float(), dim=-1)
                dense_vecs.extend(dense.tolist())
                weights = output.logits.squeeze(-1).relu().tolist()
                for ids, row in zip(inputs.input_ids.tolist(), weights, strict=True):
                    lexical = {}
                    for token_id, weight in zip(ids, row, strict=True):
                        if token_id not in self.special_ids and weight > lexical.get(token_id, 0):
                            lexical[token_id] = weight
                    lexical_weights.append(lexical)
        return {'dense_vecs': dense_vecs, 'lexical_weights': lexical_weights}

    encode_corpus = encode
