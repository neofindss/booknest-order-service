import copy

from app.errors import CatalogError


class FakeCatalogClient:
    """In-process stand-in for the catalog service used by the order tests."""

    def __init__(self):
        self.books = {
            "book-kitchen-orbits": {
                "title": "Kitchen Orbits",
                "author": "Farhan Qureshi",
                "isbn": "9781000000004",
                "unitPrice": 450.0,
                "stock": 2,
            },
            "book-rivers-of-code": {
                "title": "Rivers of Code",
                "author": "Meera Iyer",
                "isbn": "9781000000001",
                "unitPrice": 749.0,
                "stock": 8,
            },
        }
        self.reservations = {}
        self.fail_release = False
        self.release_calls = []
        self.unavailable = False

    async def reserve(self, order_id, items):
        if self.unavailable:
            raise CatalogError(503, "CATALOG_UNAVAILABLE", "Catalog service is unavailable")
        existing = self.reservations.get(order_id)
        if existing and existing["status"] == "RESERVED":
            return copy.deepcopy(existing)
        for item in items:
            book = self.books.get(item["bookId"])
            if book is None:
                raise CatalogError(404, "BOOK_NOT_FOUND", f"Book {item['bookId']} was not found")
            if book["stock"] < item["quantity"]:
                raise CatalogError(
                    409,
                    "INSUFFICIENT_STOCK",
                    f"Only {book['stock']} copies of '{book['title']}' are available",
                )
        reserved = []
        for item in items:
            book = self.books[item["bookId"]]
            book["stock"] -= item["quantity"]
            reserved.append(
                {
                    "bookId": item["bookId"],
                    "title": book["title"],
                    "author": book["author"],
                    "isbn": book["isbn"],
                    "unitPrice": book["unitPrice"],
                    "quantity": item["quantity"],
                }
            )
        payload = {"orderId": order_id, "status": "RESERVED", "items": reserved}
        self.reservations[order_id] = payload
        return copy.deepcopy(payload)

    async def release(self, order_id):
        self.release_calls.append(order_id)
        if self.fail_release:
            raise CatalogError(503, "CATALOG_UNAVAILABLE", "Catalog service is unavailable")
        existing = self.reservations.get(order_id)
        if existing is None:
            raise CatalogError(404, "RESERVATION_NOT_FOUND", "No stock reservation exists for this order")
        if existing["status"] == "RELEASED":
            return copy.deepcopy(existing)
        for item in existing["items"]:
            self.books[item["bookId"]]["stock"] += item["quantity"]
        existing["status"] = "RELEASED"
        return copy.deepcopy(existing)
