from __future__ import annotations

from app.schemas import PreferenceProfile
from app.services.vision_service import image_text_match, text_match, text_style_scores

DEMO_ENTITIES = [
    {"name": "A.P.C.", "category": "Fashion brand inspiration", "description": "French label known for understated, pared-back design.", "tags": ["Minimalist", "Contemporary classic"]},
    {"name": "Stüssy", "category": "Fashion brand inspiration", "description": "California streetwear label with roots in surf and youth culture.", "tags": ["Streetwear", "Experimental"]},
    {"name": "Dries Van Noten", "category": "Fashion brand inspiration", "description": "Belgian designer associated with expressive color and pattern.", "tags": ["Experimental", "Vintage"]},
    {"name": "Barbour", "category": "Fashion brand inspiration", "description": "British heritage outerwear brand with practical country styling.", "tags": ["Contemporary classic", "Layered"]},
    {"name": "COS", "category": "Fashion brand inspiration", "description": "Modern fashion label emphasizing considered shapes and clean design.", "tags": ["Minimalist", "Smart casual"]},
    {"name": "Levi's", "category": "Fashion brand inspiration", "description": "American denim brand with a long history in everyday and vintage style.", "tags": ["Vintage", "Streetwear"]},
    {"name": "Comme des Garçons", "category": "Fashion brand inspiration", "description": "Japanese fashion house known for conceptual and unconventional design.", "tags": ["Experimental", "Formal"]},
    {"name": "Ralph Lauren", "category": "Fashion brand inspiration", "description": "American fashion house drawing on classic tailoring and heritage references.", "tags": ["Contemporary classic", "Smart casual"]},
]


def _combined_text(profile: PreferenceProfile) -> str:
    return " ".join(part for part in [profile.description, profile.interests, profile.outcome, profile.aesthetic, profile.occasion, *profile.colors] if part).strip()


def recommend(profile: PreferenceProfile, candidates: list[dict], visual_styles: list[dict] | None = None, image_vector=None, mode: str = "demo") -> list[dict]:
    query = _combined_text(profile)
    text_scores = text_style_scores(query) if query else {}
    visual = {item["name"]: item["score"] for item in (visual_styles or [])}
    liked = [value.removeprefix("like:") for value in profile.feedback if value.startswith("like:")]
    rejected = [value.removeprefix("reject:") for value in profile.feedback if value.startswith("reject:")]
    excluded = profile.avoid.lower()
    ranked = []
    for entity in candidates:
        name = entity["name"]
        if name in rejected or (excluded and any(token.strip() and token.strip() in (name + " " + entity.get("description", "")).lower() for token in excluded.split(","))):
            continue
        tags = entity.get("tags", [])
        visual_score = max((visual.get(tag, 0.0) for tag in tags), default=None)
        text_score = max((text_scores.get(tag, 0.0) for tag in tags), default=None)
        if image_vector is not None:
            visual_score = image_text_match(image_vector, name + " " + entity.get("description", ""))
        if query:
            text_score = text_match(query, name + " " + entity.get("description", ""))
        entity_id = str(entity.get("entity_id") or name.casefold().replace(" ", "-"))
        if name in rejected or entity_id in rejected or (excluded and any(token.strip() and token.strip() in name.lower() for token in excluded.split(","))):
            continue
        cultural_score = entity.get("cultural_signal")
        signals = []
        if visual_score is not None:
            signals.append(((visual_score + 1) / 2, 0.45 if profile.emphasis == "balanced" else 0.7 if profile.emphasis == "visual" else 0.25))
        if text_score is not None:
            signals.append(((text_score + 1) / 2, 0.45 if profile.emphasis == "balanced" else 0.25 if profile.emphasis == "visual" else 0.35))
        if isinstance(cultural_score, (int, float)) and 0 <= cultural_score <= 1:
            signals.append((float(cultural_score), 0.1 if profile.emphasis != "cultural" else 0.4))
        if not signals:
            base = 0.5
        else:
            total_weight = sum(weight for _, weight in signals)
            base = sum(value * weight for value, weight in signals) / total_weight
        boost = 0.035 if name in liked or entity_id in liked else 0.0
        score = max(0.0, min(1.0, base + boost))
        reasons = []
        if tags:
            reasons.append("Associated with " + ", ".join(tag.lower() for tag in tags[:2]))
        if text_score is not None:
            reasons.append("Compared with your stated style using image-text embeddings")
        if name in liked:
            reasons.append("Elevated by your like in this session")
        if not reasons:
            reasons.append("Selected from the current inspiration set")
        ranked.append({
            "id": entity_id,
            "name": name,
            "category": entity.get("category", "Fashion inspiration"),
            "description": entity.get("description", ""),
            "explanation": ". ".join(reasons) + ".",
            "source": entity.get("source", "Curated demo catalog" if mode == "demo" else "Qloo Insights API"),
            "visual_similarity": round(float(visual_score), 4) if visual_score is not None else None,
            "text_relevance": round(float(text_score), 4) if text_score is not None else None,
            "cultural_signal": entity.get("cultural_signal"),
            "ranking_score": round(score, 4),
            "cultural_context": "Qloo brand affinity discovery" if mode == "live" else "Demo inspiration only; not a Qloo result",
        })
    return sorted(ranked, key=lambda row: row["ranking_score"], reverse=True)[:8]

