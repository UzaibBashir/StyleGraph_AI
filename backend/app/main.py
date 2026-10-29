from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.schemas import AnalysisResponse, FeedbackRequest, FeedbackResponse, PreferenceProfile
from app.services.qloo_service import QlooError, QlooService
from app.services.recommendation_service import DEMO_ENTITIES, recommend
from app.services.vision_service import analyze_image, model_is_loaded, text_style_scores

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("stylegraph")
settings = get_settings()
app = FastAPI(title="StyleGraph AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "mode": settings.mode}


@app.get("/ready")
async def ready():
    return {"status": "ready", "mode": settings.mode, "qloo_configured": bool(settings.qloo_api_key), "model": settings.model_name, "model_loaded": model_is_loaded()}


@app.post("/api/style/analyze", response_model=AnalysisResponse)
async def analyze(
    profile_json: str = Form(...),
    image: UploadFile | None = File(default=None),
    mode: str = Form(default="demo"),
):
    try:
        profile = PreferenceProfile.model_validate_json(profile_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Style preferences are invalid.") from exc
    analysis = None
    image_vector = None
    if image is not None:
        data = await image.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Image must be smaller than {settings.max_upload_mb} MB.")
        try:
            with Image.open(__import__("io").BytesIO(data)) as opened:
                if opened.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP image.")
                if opened.width * opened.height > 20_000_000:
                    raise HTTPException(status_code=413, detail="Image dimensions are too large to process safely.")
                opened.verify()
            analysis, image_vector = analyze_image(data)
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=415, detail="The uploaded file is not a valid supported image.") from exc
        except RuntimeError as exc:
            logger.exception("Vision model initialization or inference failed")
            raise HTTPException(status_code=503, detail="Image analysis is temporarily unavailable. Text-only discovery is still available.") from exc
    elif not any([profile.description, profile.interests, profile.aesthetic, profile.outcome]):
        raise HTTPException(status_code=422, detail="Add a style description or upload an outfit image to begin.")

    active_mode = "live" if mode == "live" else "demo"
    notes = []
    if analysis is None:
        text = " ".join([profile.description, profile.aesthetic, profile.occasion, profile.interests])
        scores = text_style_scores(text) if text.strip() else {}
        matches = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:4]
        analysis = {
            "description": "Text preferences compared with broad style descriptions; no image characteristics were observed.",
            "styles": [{"name": name, "score": round(score, 4)} for name, score in matches],
            "colors": [],
            "suggestions": ["Add an outfit image for visual comparison", "Try a different occasion or aesthetic"],
            "method": "OpenAI CLIP ViT-B/32 text-text cosine similarity.",
        }

    if active_mode == "live":
        if not profile.interests.strip():
            raise HTTPException(status_code=422, detail="Add a cultural reference to use live Qloo discovery.")
        qloo = QlooService()
        try:
            candidates = await qloo.brand_recommendations(profile.interests)
            if not candidates:
                notes.append("Qloo returned no brand matches for this interest. Try a more specific artist, film, or brand name.")
        except QlooError as exc:
            logger.warning("Qloo request failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            await qloo.close()
    else:
        candidates = DEMO_ENTITIES
        notes.append("Demo recommendations come from a curated sample catalog, not Qloo.")

    try:
        recommendations = recommend(profile, candidates, analysis.get("styles", []), image_vector, active_mode)
    except RuntimeError as exc:
        logger.exception("Recommendation embedding failed")
        raise HTTPException(status_code=503, detail="The style model is temporarily unavailable. Please retry.") from exc
    return {"mode": active_mode, "analysis": analysis, "recommendations": recommendations, "notes": notes}


@app.post("/api/feedback", response_model=FeedbackResponse)
async def feedback(request: FeedbackRequest):
    return {"message": f"{request.action.title()} recorded for this session. Rerun analysis to refine the ranking."}

