"""Vietnamese cross-encoder adapter for the retrieval pipeline."""

from core.pho_text import PAIR_LIMIT, segment, tokenizer


class PhoRanker:
    def __init__(self, model_name, use_fp16=False):
        import torch
        from transformers import AutoModelForSequenceClassification

        self.torch = torch
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        dtype = torch.float16 if self.device.type == 'cuda' and use_fp16 else torch.float32
        self.tokenizer = tokenizer(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name, dtype=dtype)
        self.model.to(self.device).eval()

    def compute_score(self, pairs, *, batch_size, max_length, normalize):
        scores = []
        with self.torch.inference_mode():
            for offset in range(0, len(pairs), batch_size):
                batch = pairs[offset:offset + batch_size]
                questions, passages = zip(*batch, strict=True)
                inputs = self.tokenizer(
                    [segment(question) for question in questions],
                    [segment(passage) for passage in passages],
                    padding=True, truncation=True, max_length=min(max_length, PAIR_LIMIT), return_tensors='pt',
                ).to(self.device)
                logits = self.model(**inputs).logits.squeeze(-1).float()
                scores.extend((logits.sigmoid() if normalize else logits).tolist())
        return scores
