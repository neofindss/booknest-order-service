import logging

import httpx

from app.errors import CatalogError

logger = logging.getLogger("order-service")


class CatalogClient:
    """Synchronous HTTP collaboration with the catalog service.

    Reserve and release are idempotent for an order id, so a lost response can be retried once.
    """

    def __init__(self, base_url: str, client: httpx.AsyncClient):
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def reserve(self, order_id: str, items: list[dict]) -> dict:
        logger.info("Calling catalog to reserve stock for order %s", order_id)
        response = await self._send(
            "POST",
            f"{self.base_url}/api/v1/reservations",
            {"orderId": order_id, "items": items},
        )
        return response

    async def release(self, order_id: str) -> dict:
        logger.info("Calling catalog to release stock for order %s", order_id)
        return await self._send("POST", f"{self.base_url}/api/v1/reservations/{order_id}/release", None)

    async def _send(self, method: str, url: str, payload: dict | None) -> dict:
        last_error = None
        for attempt in range(2):
            try:
                response = await self.client.request(method, url, json=payload)
                break
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Catalog call failed (attempt %s): %s", attempt + 1, exc)
        else:
            raise CatalogError(503, "CATALOG_UNAVAILABLE", "Catalog service is unavailable") from last_error

        if response.status_code >= 400:
            body = _error_body(response)
            raise CatalogError(response.status_code, body["error"], body["message"])
        return response.json()


def _error_body(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except Exception:
        return {"error": "CATALOG_ERROR", "message": "Catalog service returned an error"}
    return {
        "error": body.get("error", "CATALOG_ERROR"),
        "message": body.get("message", "Catalog service returned an error"),
    }
