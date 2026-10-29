from __future__ import annotations

from functools import lru_cache
from io import BytesIO

import numpy as np
import open_clip
import torch
from PIL import Image, ImageOps
from sklearn.cluster import KMeans

from app.config import get_settings

STYLE_PROMPTS = {
    "Minimalist": "a minimalist outfit with clean lines, neutral tones and simple shapes",
    "Vintage": "a vintage inspired outfit with retro silhouettes and nostalgic details",
    "Streetwear": "a contemporary streetwear outfit with relaxed proportions and urban styling",
    "Smart casual": "a smart casual outfit balancing polished pieces with relaxed styling",
    "Formal": "a formal outfit with tailored proportions and refined styling",
    "Monochrome": "a monochrome outfit built around a single color family",
    "Layered": "a layered outfit combining multiple garments and textures",
    "Experimental": "an experimental fashion look with expressive proportions and unexpected combinations",
    "Contemporary classic": "a contemporary classic outfit with timeless shapes and modern details",
}

COLOR_NAMES = {
    "black": (0, 0, 0), "white": (245, 245, 240), "gray": (128, 128, 128),
    "navy": (25, 45, 85), "blue": (45, 105, 190), "red": (200, 45, 55),
    "orange": (230, 125, 45), "yellow": (235, 205, 65), "green": (65, 135, 80),
    "purple": (125, 75, 155), "pink": (220, 125, 155), "brown": (125, 80, 50),
    "beige": (205, 185, 145),
}


@lru_cache(maxsize=1)
def _load_model():
    settings = get_settings()
    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.model_name, pretrained=settings.model_pretrained, device="cpu"
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(settings.model_name)
    return model, preprocess, tokenizer


def model_is_loaded() -> bool:
    return _load_model.cache_info().currsize > 0


def _normalized(vector: torch.Tensor) -> torch.Tensor:
    return vector / vector.norm(dim=-1, keepdim=True).clamp(min=1e-12)


def _text_embedding(text: str) -> torch.Tensor:
    model, _, tokenizer = _load_model()
    with torch.inference_mode():
        return _normalized(model.encode_text(tokenizer([text])))


def image_embedding(raw: bytes) -> tuple[torch.Tensor, Image.Image]:
    model, preprocess, _ = _load_model()
    image = Image.open(BytesIO(raw))
    image = ImageOps.exif_transpose(image).convert("RGB")
    with torch.inference_mode():
        vector = _normalized(model.encode_image(preprocess(image).unsqueeze(0)))
    return vector, image


def _color_palette(image: Image.Image) -> list[dict[str, str]]:
    pixels = np.asarray(image.resize((96, 96)), dtype=np.uint8).reshape(-1, 3)
    sample = pixels[:: max(1, len(pixels) // 1200)]
    count = min(4, len(np.unique(sample, axis=0)))
    if count < 1:
        return []
    centers = KMeans(n_clusters=count, n_init=3, random_state=17).fit(sample).cluster_centers_
    palette = []
    for center in centers:
        rgb = tuple(int(value) for value in center)
        name = min(COLOR_NAMES, key=lambda key: sum((rgb[i] - COLOR_NAMES[key][i]) ** 2 for i in range(3)))
        palette.append({"name": name.title(), "hex": "#%02X%02X%02X" % rgb})
    return palette


def analyze_image(raw: bytes) -> tuple[dict, torch.Tensor]:
    vector, image = image_embedding(raw)
    style_names = list(STYLE_PROMPTS)
    prompts = _load_model()[2]([STYLE_PROMPTS[name] for name in style_names])
    with torch.inference_mode():
        text_vectors = _normalized(_load_model()[0].encode_text(prompts))
        scores = (vector @ text_vectors.T).squeeze(0)
    ranked = sorted(zip(style_names, scores.tolist()), key=lambda row: row[1], reverse=True)[:4]
    styles = [{"name": name, "score": round(float(score), 4)} for name, score in ranked]
    labels = ", ".join(item["name"].lower() for item in styles[:2])
    return {
        "description": f"The image has visual similarities to {labels} styling. This is a broad aesthetic match, not garment identification.",
        "styles": styles,
        "colors": _color_palette(image),
        "suggestions": [f"Explore {styles[0]['name'].lower()} references", "Try a related color palette"],
        "method": "OpenAI CLIP ViT-B/32 image-text cosine similarity; approximate palette from image pixels.",
    }, vector


def text_style_scores(text: str) -> dict[str, float]:
    user_vector = _text_embedding(text)
    model, _, tokenizer = _load_model()
    names = list(STYLE_PROMPTS)
    with torch.inference_mode():
        candidates = _normalized(model.encode_text(tokenizer([STYLE_PROMPTS[name] for name in names])))
        values = (user_vector @ candidates.T).squeeze(0).tolist()
    return {name: float(score) for name, score in zip(names, values)}


def text_match(text: str, candidate: str) -> float | None:
    if not text.strip():
        return None
    return float((_text_embedding(text) @ _text_embedding(candidate).T).item())


def image_text_match(image_vector: torch.Tensor, candidate: str) -> float:
    model, _, tokenizer = _load_model()
    with torch.inference_mode():
        candidate_vector = _normalized(model.encode_text(tokenizer([candidate])))
    return float((image_vector @ candidate_vector.T).item())

