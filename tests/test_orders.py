from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import InMemoryOrderRepository
from tests.fake_catalog import FakeCatalogClient


def make_client(repo=None, catalog=None):
    repo = repo or InMemoryOrderRepository()
    catalog = catalog or FakeCatalogClient()
    app = create_app(repo=repo, catalog=catalog)
    return TestClient(app), catalog


def place(client, book_id="book-kitchen-orbits", quantity=1, email="ananya.shah@example.com"):
    return client.post(
        "/api/v1/orders",
        json={
            "customerName": "Ananya Shah",
            "customerEmail": email,
            "items": [{"bookId": book_id, "quantity": quantity}],
        },
    )


def test_health():
    client, _catalog = make_client()
    assert client.get("/health").json()["service"] == "order-service"
    assert client.get("/ready").status_code == 200


def test_place_order_uses_catalog_price_and_reduces_stock():
    client, catalog = make_client()
    response = place(client, quantity=2)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PLACED"
    assert body["items"][0]["unitPrice"] == 450
    assert body["items"][0]["lineTotal"] == 900
    assert body["totalAmount"] == 900
    assert catalog.books["book-kitchen-orbits"]["stock"] == 0
    assert "order-1" not in body["id"]


def test_insufficient_stock_does_not_create_an_order():
    client, catalog = make_client()
    response = place(client, quantity=3)
    assert response.status_code == 409
    assert response.json()["error"] == "INSUFFICIENT_STOCK"
    assert catalog.books["book-kitchen-orbits"]["stock"] == 2
    assert client.get("/api/v1/orders").json()["total"] == 0


def test_unknown_book_is_reported():
    client, _catalog = make_client()
    response = place(client, book_id="missing-book")
    assert response.status_code == 404
    assert response.json()["error"] == "BOOK_NOT_FOUND"


def test_catalog_outage_returns_503():
    catalog = FakeCatalogClient()
    catalog.unavailable = True
    client, _catalog = make_client(catalog=catalog)
    response = place(client)
    assert response.status_code == 503
    assert response.json()["error"] == "CATALOG_UNAVAILABLE"


def test_duplicate_line_is_rejected_before_calling_catalog():
    client, catalog = make_client()
    response = client.post(
        "/api/v1/orders",
        json={
            "customerName": "Ananya Shah",
            "customerEmail": "ananya.shah@example.com",
            "items": [
                {"bookId": "book-kitchen-orbits", "quantity": 1},
                {"bookId": "book-kitchen-orbits", "quantity": 1},
            ],
        },
    )
    assert response.status_code == 400
    assert catalog.books["book-kitchen-orbits"]["stock"] == 2


def test_cancel_releases_stock_and_is_idempotent():
    client, catalog = make_client()
    created = place(client, quantity=2).json()
    cancelled = client.post(f"/api/v1/orders/{created['id']}/cancellations")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert catalog.books["book-kitchen-orbits"]["stock"] == 2

    again = client.post(f"/api/v1/orders/{created['id']}/cancellations")
    assert again.json()["status"] == "CANCELLED"
    assert catalog.books["book-kitchen-orbits"]["stock"] == 2


def test_cancel_does_not_change_order_when_catalog_is_down():
    catalog = FakeCatalogClient()
    client, catalog = make_client(catalog=catalog)
    created = place(client).json()
    catalog.fail_release = True
    response = client.post(f"/api/v1/orders/{created['id']}/cancellations")
    assert response.status_code == 503
    assert client.get(f"/api/v1/orders/{created['id']}").json()["status"] == "PLACED"


def test_list_filters_by_customer_and_get_missing_order():
    client, _catalog = make_client()
    place(client, email="ananya.shah@example.com")
    place(client, book_id="book-rivers-of-code", email="rohan.das@example.com")
    listed = client.get("/api/v1/orders", params={"customerEmail": "ROHAN.DAS@example.com"})
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["customerEmail"] == "rohan.das@example.com"
    missing = client.get("/api/v1/orders/does-not-exist")
    assert missing.status_code == 404


def test_failed_save_releases_the_reservation():
    class FailingRepository(InMemoryOrderRepository):
        async def insert(self, order):
            raise RuntimeError("disk full")

    catalog = FakeCatalogClient()
    client, catalog = make_client(repo=FailingRepository(), catalog=catalog)
    response = place(client, quantity=2)
    assert response.status_code == 500
    assert response.json()["error"] == "ORDER_PERSISTENCE_FAILED"
    assert catalog.books["book-kitchen-orbits"]["stock"] == 2
    assert catalog.reservations[next(iter(catalog.reservations))]["status"] == "RELEASED"


def test_release_is_attempted_when_reserve_times_out():
    catalog = FakeCatalogClient()
    catalog.unavailable = True
    client, catalog = make_client(catalog=catalog)
    response = place(client)
    assert response.status_code == 503
    assert response.json()["error"] == "CATALOG_UNAVAILABLE"
    assert len(catalog.release_calls) == 1


def test_release_is_not_attempted_on_client_errors():
    client, catalog = make_client()
    response = place(client, quantity=3)
    assert response.status_code == 409
    assert catalog.release_calls == []


def test_validation_error_uses_error_envelope():
    client, catalog = make_client()
    response = client.post(
        "/api/v1/orders",
        json={
            "customerName": "Ananya Shah",
            "customerEmail": "ananya.shah@example.com",
            "items": [{"bookId": "book-kitchen-orbits", "quantity": 0}],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert "items.0.quantity" in body["message"]
    assert catalog.release_calls == []
