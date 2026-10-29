import asyncio

import httpx

from app.config import get_settings
from app.services.qloo_service import QlooService


def test_qloo_search_then_brand_insights_contract(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "qloo_api_key", "test-key")
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": {"entities": [{"entity_id": "entity-123"}]}})
        return httpx.Response(200, json={"results": {"entities": [{
            "name": "Example Label",
            "entity_id": "brand-456",
            "properties": {"description": "A test brand."},
            "query": {"affinity": 0.72},
        }]}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://hackathon.api.qloo.com", headers={"X-Api-Key": "test-key"})
    service = QlooService(client)
    async def request_brands():
        try:
            return await service.brand_recommendations("Example Film")
        finally:
            await client.aclose()

    brands = asyncio.run(request_brands())

    assert len(calls) == 2
    assert calls[0].url.path == "/search"
    assert calls[0].url.params["query"] == "Example Film"
    assert calls[1].url.path == "/v2/insights"
    assert calls[1].url.params["filter.type"] == "urn:entity:brand"
    assert calls[1].url.params["signal.interests.entities"] == "entity-123"
    assert brands[0]["description"] == "A test brand."
    assert brands[0]["cultural_signal"] == 0.72
    assert brands[0]["source"] == "Qloo Insights API"

