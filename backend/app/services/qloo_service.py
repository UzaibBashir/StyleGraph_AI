from __future__ import annotations

import httpx

from app.config import get_settings


class QlooError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class QlooService:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.settings = get_settings()
        self.client = client or httpx.AsyncClient(
            base_url=self.settings.qloo_base_url.rstrip("/"),
            headers={"X-Api-Key": self.settings.qloo_api_key},
            timeout=httpx.Timeout(12.0),
        )
        self.owns_client = client is None

    async def _get(self, path: str, params: dict[str, str]) -> dict:
        for attempt in range(2):
            try:
                response = await self.client.get(path, params=params)
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    continue
                raise QlooError("Qloo request timed out. Please retry shortly.") from exc
            except httpx.HTTPError as exc:
                raise QlooError("Qloo could not be reached. Please retry shortly.") from exc
            if response.status_code == 429:
                raise QlooError("Qloo rate limit reached. Please retry later.", 429)
            if response.status_code in (401, 403):
                raise QlooError("Qloo rejected the API key or requested entity type.", response.status_code)
            if response.status_code >= 500 and attempt == 0:
                continue
            if response.is_error:
                raise QlooError(f"Qloo returned HTTP {response.status_code}.", response.status_code)
            try:
                payload = response.json()
            except ValueError as exc:
                raise QlooError("Qloo returned an unreadable response.") from exc
            if not isinstance(payload, dict):
                raise QlooError("Qloo returned an unexpected response shape.")
            return payload
        raise QlooError("Qloo request failed after a retry.")

    async def brand_recommendations(self, interest: str) -> list[dict]:
        if not self.settings.qloo_api_key:
            raise QlooError("Live mode needs QLOO_API_KEY configured on the backend.")
        query = interest.strip()
        if not query:
            return []
        search = await self._get("/search", {"query": query, "types": "urn:entity:artist,urn:entity:brand,urn:entity:movie", "take": "5"})
        search_results = search.get("results")
        if not isinstance(search_results, dict) or not isinstance(search_results.get("entities", []), list):
            raise QlooError("Qloo entity search returned an unexpected response shape.")
        entities = search_results.get("entities", [])
        entity_id = next((item.get("entity_id") or item.get("id") for item in entities if item.get("entity_id") or item.get("id")), None)
        if not entity_id:
            return []
        result = await self._get("/v2/insights", {
            "filter.type": "urn:entity:brand",
            "signal.interests.entities": entity_id,
            "take": "12",
        })
        insight_results = result.get("results")
        if not isinstance(insight_results, dict) or not isinstance(insight_results.get("entities", []), list):
            raise QlooError("Qloo brand insights returned an unexpected response shape.")
        candidates = insight_results.get("entities", [])
        normalized = []
        for entity in candidates:
            name = entity.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            normalized.append({
                "name": name.strip(),
                "category": "Fashion brand inspiration",
                "description": entity.get("description") or (entity.get("properties") or {}).get("description", ""),
                "entity_id": entity.get("entity_id") or entity.get("id"),
                "cultural_signal": self._affinity(entity),
                "source": "Qloo Insights API",
            })
        return normalized

    @staticmethod
    def _affinity(entity: dict) -> float | None:
        value = entity.get("query", {}).get("affinity")
        if isinstance(value, (int, float)) and 0 <= value <= 1:
            return float(value)
        return None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

