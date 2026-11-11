import logging
import uuid

from app.errors import AppError, CatalogError
from app.schemas import PlaceOrder
from app.timeutil import iso_now

logger = logging.getLogger("order-service")


class OrderService:
    """Order commands and queries.

    The order service stores orders only. Prices and stock decisions come from the catalog service.
    """

    def __init__(self, repo, catalog):
        self.repo = repo
        self.catalog = catalog

    async def place_order(self, data: PlaceOrder) -> dict:
        book_ids = [item.bookId for item in data.items]
        if len(set(book_ids)) != len(book_ids):
            raise AppError(400, "DUPLICATE_BOOK", "Each book can appear only once in an order")

        order_id = str(uuid.uuid4())
        try:
            reservation = await self.catalog.reserve(
                order_id,
                [{"bookId": item.bookId, "quantity": item.quantity} for item in data.items],
            )
        except CatalogError as exc:
            if exc.status_code == 503:
                # Both attempts failed, but the catalog may have committed the reservation.
                # Best-effort release; a 404 RESERVATION_NOT_FOUND is the expected, harmless outcome.
                try:
                    await self.catalog.release(order_id)
                except Exception as release_exc:
                    logger.warning(
                        "Best-effort release after reserve timeout for order %s did not succeed: %s",
                        order_id,
                        release_exc,
                    )
            raise AppError(exc.status_code, exc.code, exc.message) from exc

        items = []
        total = 0.0
        for item in reservation["items"]:
            line_total = round(item["unitPrice"] * item["quantity"], 2)
            total = round(total + line_total, 2)
            items.append(
                {
                    "bookId": item["bookId"],
                    "title": item["title"],
                    "author": item["author"],
                    "isbn": item["isbn"],
                    "unitPrice": item["unitPrice"],
                    "quantity": item["quantity"],
                    "lineTotal": line_total,
                }
            )

        now = iso_now()
        order = {
            "id": order_id,
            "customerName": data.customerName.strip(),
            "customerEmail": data.customerEmail.strip(),
            "items": items,
            "status": "PLACED",
            "totalAmount": total,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            return await self.repo.insert(order)
        except Exception as exc:
            logger.exception("Failed to persist order %s; releasing reserved stock", order_id)
            try:
                await self.catalog.release(order_id)
            except Exception:
                logger.exception("Compensation release failed for order %s", order_id)
            raise AppError(
                500,
                "ORDER_PERSISTENCE_FAILED",
                "The order could not be saved and the stock reservation was released",
            ) from exc

    async def cancel_order(self, order_id: str) -> dict:
        order = await self.repo.get(order_id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Order was not found")
        if order["status"] == "CANCELLED":
            return order
        try:
            await self.catalog.release(order_id)
        except CatalogError as exc:
            raise AppError(exc.status_code, exc.code, exc.message) from exc
        updated = await self.repo.update(order_id, {"status": "CANCELLED", "updatedAt": iso_now()})
        logger.info("Cancelled order %s", order_id)
        return updated

    async def get_order(self, order_id: str) -> dict:
        order = await self.repo.get(order_id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Order was not found")
        return order

    async def list_orders(self, email: str | None, page: int, page_size: int) -> dict:
        items, total = await self.repo.list_orders(email, (page - 1) * page_size, page_size)
        return {"items": items, "page": page, "pageSize": page_size, "total": total}
