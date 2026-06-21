"""OpenCLIP embedder adapter (production). Heavy deps imported lazily.

Joint image/text embedding space enables cross-modal search (text query -> symbol crop) and is
the foundation for future RAG. Implements the same ``Embedder`` port as HashEmbedder.
"""

from __future__ import annotations

import io

from ...domain.ports import Embedder


class OpenClipEmbedder(Embedder):
    def __init__(self, model_name: str, pretrained: str, dim: int) -> None:
        self._model_name = model_name
        self._pretrained = pretrained
        self._dim = dim
        self._model = None
        self._preprocess = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import open_clip  # pragma: no cover - heavy
        import torch  # noqa: F401  # pragma: no cover

        model, _, preprocess = open_clip.create_model_and_transforms(
            self._model_name, pretrained=self._pretrained
        )
        model.eval()
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(self._model_name)

    @property
    def model_name(self) -> str:
        return f"openclip-{self._model_name}-{self._pretrained}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed_image(self, crop_png: bytes) -> list[float]:  # pragma: no cover - heavy
        import torch
        from PIL import Image

        self._ensure_loaded()
        image = Image.open(io.BytesIO(crop_png)).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0)
        with torch.no_grad():
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].tolist()

    def embed_text(self, text: str) -> list[float]:  # pragma: no cover - heavy
        import torch

        self._ensure_loaded()
        tokens = self._tokenizer([text])
        with torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].tolist()
