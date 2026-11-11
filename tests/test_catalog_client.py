import asyncio

import httpx
import pytest

from app.catalog_client import CatalogClient
from app.errors import CatalogError

BASE_URL = "http://catalog.test"
ITEMS = [{"bookId": "book-1", "quantity": 1}]


def make_client(handler):
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CatalogClient(BASE_URL, http_client), http_client


def run_reserve(handler):
    async def scenario():
        client, http_client = make_client(handler)
        try:
            return await client.reserve("order-1", ITEMS)
        finally:
            await http_client.aclose()

    return asyncio.run(scenario())


def test_reserve_success_returns_body_and_posts_expected_request():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"orderId": "order-1", "status": "RESERVED", "items": []})

    body = run_reserve(handler)
    assert body["status"] == "RESERVED"
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == f"{BASE_URL}/api/v1/reservations"
    assert b'"orderId"' in seen[0].content


def test_conflict_is_mapped_to_catalog_error_with_body_code_and_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "INSUFFICIENT_STOCK", "message": "Only 1 copy left"})

    with pytest.raises(CatalogError) as caught:
        run_reserve(handler)
    assert caught.value.status_code == 409
    assert caught.value.code == "INSUFFICIENT_STOCK"
    assert caught.value.message == "Only 1 copy left"


def test_non_json_server_error_is_mapped_to_catalog_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>boom</html>")

    with pytest.raises(CatalogError) as caught:
        run_reserve(handler)
    assert caught.value.status_code == 500
    assert caught.value.code == "CATALOG_ERROR"


def test_connection_failure_is_retried_once_then_reported_unavailable():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(CatalogError) as caught:
        run_reserve(handler)
    assert len(attempts) == 2
    assert caught.value.status_code == 503
    assert caught.value.code == "CATALOG_UNAVAILABLE"


def test_connection_failure_then_success_uses_the_retry():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(200, json={"orderId": "order-1", "status": "RESERVED", "items": []})

    assert run_reserve(handler)["status"] == "RESERVED"
    assert len(attempts) == 2
