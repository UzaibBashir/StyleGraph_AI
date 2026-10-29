from typing import Literal

from pydantic import BaseModel, Field


class PreferenceProfile(BaseModel):
    description: str = ""
    interests: str = ""
    outcome: str = ""
    aesthetic: str = ""
    occasion: str = ""
    colors: list[str] = Field(default_factory=list)
    budget: str = ""
    avoid: str = ""
    emphasis: Literal["balanced", "visual", "cultural"] = "balanced"
    feedback: list[str] = Field(default_factory=list)


class StyleMatch(BaseModel):
    name: str
    score: float


class Color(BaseModel):
    name: str
    hex: str


class VisualAnalysis(BaseModel):
    description: str
    styles: list[StyleMatch]
    colors: list[Color]
    suggestions: list[str]
    method: str


class Recommendation(BaseModel):
    id: str
    name: str
    category: str
    description: str = ""
    explanation: str
    source: str
    visual_similarity: float | None = None
    text_relevance: float | None = None
    cultural_signal: float | None = None
    ranking_score: float
    cultural_context: str = ""


class AnalysisResponse(BaseModel):
    mode: Literal["live", "demo"]
    analysis: VisualAnalysis | None = None
    recommendations: list[Recommendation]
    notes: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    recommendation_id: str
    action: Literal["like", "reject"]


class FeedbackResponse(BaseModel):
    message: str
    session_only: bool = True

