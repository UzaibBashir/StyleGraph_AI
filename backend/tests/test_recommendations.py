from app.schemas import PreferenceProfile
from app.services.recommendation_service import recommend


def test_feedback_changes_demo_recommendations():
    profile = PreferenceProfile(feedback=["like:Stüssy", "reject:A.P.C."])
    results = recommend(profile, [
        {"name": "A.P.C.", "tags": ["Minimalist"]},
        {"name": "Stüssy", "tags": ["Streetwear"]},
    ])
    assert [item["name"] for item in results] == ["Stüssy"]
    assert "like in this session" in results[0]["explanation"]
    assert results[0]["source"] == "Curated demo catalog"
    assert results[0]["cultural_signal"] is None

