from __future__ import annotations

import os
import sys
import asyncio
from io import BytesIO
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from PIL import Image, UnidentifiedImageError


def _secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        value = None
    return str(value) if value else default


for _name in ("QLOO_API_KEY", "QLOO_BASE_URL", "BACKEND_MODE", "MAX_UPLOAD_MB", "MODEL_NAME", "MODEL_PRETRAINED"):
    if _name not in os.environ:
        _value = _secret(_name)
        if _value:
            os.environ[_name] = _value

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.schemas import PreferenceProfile
from app.services.qloo_service import QlooError, QlooService
from app.services.recommendation_service import DEMO_ENTITIES, recommend
from app.services.vision_service import analyze_image, text_style_scores


def _run_qloo(interest: str) -> list[dict]:
    async def request() -> list[dict]:
        qloo = QlooService()
        try:
            return await qloo.brand_recommendations(interest)
        finally:
            await qloo.close()

    return asyncio.run(request())


def _analyze_uploaded_image(raw: bytes) -> tuple[dict, object]:
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "8"))
    if len(raw) > max_upload_mb * 1024 * 1024:
        raise ValueError(f"Image must be smaller than {max_upload_mb} MB.")
    try:
        with Image.open(BytesIO(raw)) as opened:
            if opened.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Upload a JPEG, PNG, or WebP image.")
            if opened.width * opened.height > 20_000_000:
                raise ValueError("Image dimensions are too large to process safely.")
            opened.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a valid supported image.") from exc
    return analyze_image(raw)


st.set_page_config(page_title="StyleGraph AI", page_icon="✳", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
.stApp { background: radial-gradient(ellipse at 88% 2%, #2b3422 0%, transparent 31%), #11120f; }
.block-container { max-width: 1180px; padding-top: 1.3rem; }
.eyebrow { color:#c8ff5a; text-transform:uppercase; letter-spacing:.17em; font:12px 'DM Mono',monospace; }
.hero { border:1px solid #353a2e; border-radius:26px; padding:62px 60px; background:linear-gradient(125deg,rgba(200,255,90,.09),rgba(255,255,255,.018) 45%,rgba(115,124,255,.08)); margin:24px 0 34px; }
.hero h1 { font-size:clamp(42px,7vw,76px); line-height:.99; letter-spacing:-.07em; max-width:760px; margin:18px 0; }
.hero p { color:#b0b3a8; font-size:17px; max-width:610px; line-height:1.7; }
.panel { background:#191b17; border:1px solid #30332b; border-radius:20px; padding:24px; }
.tag { display:inline-block; padding:8px 12px; border-radius:99px; border:1px solid #3a4032; color:#d3d5ca; font:11px 'DM Mono',monospace; margin:5px 5px 5px 0; }
.muted { color:#a3a69b; }
.card { border:1px solid #35382f; background:linear-gradient(145deg,#1c1f19,#171915); border-radius:18px; padding:22px; height:100%; }
.card h3 { margin:0 0 8px; letter-spacing:-.035em; }
.metric { font:12px 'DM Mono',monospace; color:#c8ff5a; }
div[data-testid="stForm"] { border:0; padding:0; }
button[kind="primary"] { border-radius:999px; font-weight:800; }
@media(max-width:700px){.hero{padding:34px 24px}.block-container{padding-left:1rem;padding-right:1rem}}
</style>
""", unsafe_allow_html=True)

if "feedback" not in st.session_state:
    st.session_state.feedback = {}
if "results" not in st.session_state:
    st.session_state.results = None

st.markdown('<div class="eyebrow">STYLE INTELLIGENCE · CULTURE IN CONTEXT</div>', unsafe_allow_html=True)
st.markdown('<section class="hero"><div class="eyebrow">Your aesthetic. Your culture. Your style.</div><h1>Dress like your world.</h1><p>Discover a personal style direction through visual AI and cultural connections. Bring an outfit, a mood, or the artists and films you love.</p></section>', unsafe_allow_html=True)

left, right = st.columns([1.08, .92], gap="large")
with left:
    st.markdown("### Build your style signal")
    st.caption("Use an image, words, or both. Your upload is analyzed in memory and is not saved by this app.")
    uploaded = st.file_uploader("An outfit photo (optional)", type=["jpg", "jpeg", "png", "webp"], help="JPEG, PNG, or WebP · up to 8 MB")
    if uploaded:
        st.image(uploaded, caption="Your image · ready for visual analysis", use_container_width=True)
    description = st.text_area("Describe your style", placeholder="Clean silhouettes, relaxed tailoring, muted colors…", height=92)
    interest = st.text_input("Cultural references", placeholder="An artist, film, place, brand, or scene you love")
    outcome = st.text_input("What are you looking for?", placeholder="Ideas for everyday outfits, a sharper work look…")
    col_a, col_b = st.columns(2)
    with col_a:
        aesthetic = st.selectbox("Aesthetic", ["Open brief", "Minimalist", "Streetwear", "Vintage", "Luxury", "Classic", "Experimental"])
        occasion = st.selectbox("Occasion", ["Any occasion", "Everyday", "College", "Work", "Formal event", "Party"])
    with col_b:
        colors = st.multiselect("Colors", ["Black", "White", "Gray", "Navy", "Blue", "Red", "Green", "Brown", "Beige"])
        emphasis = st.selectbox("Recommendation focus", ["Balanced", "Visual similarity", "Cultural discovery"])
    col_c, col_d = st.columns(2)
    with col_c:
        budget = st.text_input("Budget (optional)", placeholder="e.g. Under ₹10,000")
    with col_d:
        avoid = st.text_input("Avoid (optional)", placeholder="e.g. logos, skinny fits")
    mode_label = st.radio("Discovery mode", ["Demo · curated inspiration", "Live · Qloo cultural graph"], horizontal=True)
    if mode_label.startswith("Live"):
        st.caption("Live mode requires a Qloo key on the backend and a cultural reference to look up.")
    if st.button("Analyze My Style", type="primary", use_container_width=True):
        if not any([uploaded, description, interest, aesthetic != "Open brief", outcome]):
            st.error("Add a style description, cultural reference, aesthetic, or outfit image to begin.")
        else:
            profile = {
                "description": description,
                "interests": interest,
                "outcome": outcome,
                "aesthetic": "" if aesthetic == "Open brief" else aesthetic,
                "occasion": "" if occasion == "Any occasion" else occasion,
                "colors": colors,
                "budget": budget,
                "avoid": avoid,
                "emphasis": {"Balanced": "balanced", "Visual similarity": "visual", "Cultural discovery": "cultural"}[emphasis],
                "feedback": [f"{action}:{name}" for name, action in st.session_state.feedback.items()],
            }
            try:
                with st.spinner("Reading the visual signal and finding relevant inspiration…"):
                    preference_profile = PreferenceProfile.model_validate(profile)
                    analysis = None
                    image_vector = None
                    if uploaded:
                        analysis, image_vector = _analyze_uploaded_image(uploaded.getvalue())
                    else:
                        text = " ".join(
                            [preference_profile.description, preference_profile.aesthetic,
                             preference_profile.occasion, preference_profile.interests]
                        )
                        scores = text_style_scores(text) if text.strip() else {}
                        matches = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:4]
                        analysis = {
                            "description": "Text preferences compared with broad style descriptions; no image characteristics were observed.",
                            "styles": [{"name": name, "score": round(score, 4)} for name, score in matches],
                            "colors": [],
                            "suggestions": ["Add an outfit image for visual comparison", "Try a different occasion or aesthetic"],
                            "method": "OpenAI CLIP ViT-B/32 text-text cosine similarity.",
                        }
                    active_mode = "live" if mode_label.startswith("Live") else "demo"
                    notes = []
                    if active_mode == "live":
                        candidates = _run_qloo(preference_profile.interests)
                        if not candidates:
                            notes.append("Qloo returned no brand matches for this interest. Try a more specific artist, film, or brand name.")
                    else:
                        candidates = DEMO_ENTITIES
                        notes.append("Demo recommendations come from a curated sample catalog, not Qloo.")
                    recommendations = recommend(
                        preference_profile,
                        candidates,
                        analysis.get("styles", []),
                        image_vector,
                        active_mode,
                    )
                    st.session_state.results = {
                        "mode": active_mode,
                        "analysis": analysis,
                        "recommendations": recommendations,
                        "notes": notes,
                    }
            except QlooError as exc:
                st.error(str(exc))
            except RuntimeError:
                st.error("The style model is temporarily unavailable. Please retry.")
            except (OSError, ValueError) as exc:
                st.error(f"Analysis failed: {exc}")

with right:
    st.markdown("### Three signals, one point of view")
    st.markdown('<div class="panel"><span class="eyebrow">01 · VISUAL</span><h3>See the aesthetic</h3><p class="muted">CLIP compares the outfit image with broad style descriptions and finds approximate colors.</p><span class="tag">Image-text embeddings</span><span class="tag">Color palette</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:12px"></div><div class="panel"><span class="eyebrow">02 · CULTURE</span><h3>Connect your references</h3><p class="muted">In live mode, Qloo’s documented entity search and Insights API surface brand inspiration connected to a cultural reference.</p><span class="tag">Optional Qloo API</span><span class="tag">No made-up scores</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:12px"></div><div class="panel"><span class="eyebrow">03 · REFINE</span><h3>Make it yours</h3><p class="muted">Like or reject ideas. Your current session feedback changes the next ranking.</p><span class="tag">Session-only feedback</span></div>', unsafe_allow_html=True)
    st.markdown("<br><div class='eyebrow'>A FEW AESTHETIC STARTING POINTS</div><span class='tag'>MINIMALIST</span><span class='tag'>VINTAGE</span><span class='tag'>STREETWEAR</span><span class='tag'>CONTEMPORARY CLASSIC</span><span class='tag'>EXPERIMENTAL</span>", unsafe_allow_html=True)

result = st.session_state.results
if result:
    st.markdown("---")
    label = "LIVE · QLOO INSIGHTS API" if result["mode"] == "live" else "DEMO · CURATED SAMPLE CATALOG"
    st.markdown(f'<div class="eyebrow">{label}</div><h2>Your style reading</h2>', unsafe_allow_html=True)
    analysis = result.get("analysis") or {}
    a, b = st.columns([1.2, .8], gap="large")
    with a:
        st.markdown(f"**Visual and preference read**  \n{analysis.get('description', '')}")
        st.caption(analysis.get("method", ""))
        if analysis.get("styles"):
            st.markdown("**Style similarities**")
            cols = st.columns(min(4, len(analysis["styles"])))
            for col, style in zip(cols, analysis["styles"]):
                col.metric(style["name"], f"{style['score']:.2f}")
    with b:
        if analysis.get("colors"):
            st.markdown("**Approximate image colors**")
            chips = "".join(f"<span style='display:inline-block;width:36px;height:36px;border-radius:50%;background:{c['hex']};border:1px solid #777;margin:5px' title='{c['name']}'></span>" for c in analysis["colors"])
            st.markdown(chips, unsafe_allow_html=True)
            st.caption("Approximate pixel palette · " + ", ".join(c["name"] for c in analysis["colors"]))
    for note in result.get("notes", []):
        st.info(note)
    st.markdown("### Inspiration, ranked for your brief")
    st.caption("Ranking scores combine available visual and text signals; they are not probabilities or Qloo affinity scores.")
    cards = st.columns(2, gap="medium")
    for index, item in enumerate(result.get("recommendations", [])):
        with cards[index % 2]:
            st.markdown(f"<div class='card'><div class='eyebrow'>{item['category']}</div><h3>{item['name']}</h3><p class='muted'>{item.get('description') or 'Cultural inspiration connected to your selected reference.'}</p><p>{item['explanation']}</p><span class='metric'>{item['source']} · rank {item['ranking_score']:.2f}</span></div>", unsafe_allow_html=True)
            key = item["id"]
            lcol, rcol = st.columns(2)
            if lcol.button("Like", key=f"like-{key}"):
                st.session_state.feedback[key] = "like"
                st.toast("Saved for this session. Analyze again to refine the ranking.")
            if rcol.button("Not for me", key=f"reject-{key}"):
                st.session_state.feedback[key] = "reject"
                st.toast("Removed from your next session ranking.")
    if result.get("mode") == "live" and not result.get("recommendations"):
        st.warning("No live Qloo brand inspirations were returned. Refine the cultural reference and try again, or choose demo mode.")

st.markdown("---")
st.caption("StyleGraph AI · Broad aesthetic similarities, not garment or brand recognition. Images are processed in memory and not retained by the application. Feedback lasts for this browser session only.")
