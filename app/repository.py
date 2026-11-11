import copy
import re
from typing import Any


def _copy(document: dict | None) -> dict | None:
    if document is None:
        return None
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


class InMemoryOrderRepository:
    def __init__(self):
        self.orders: dict[str, dict] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def insert(self, order: dict) -> dict:
        self.orders[order["id"]] = copy.deepcopy(order)
        return copy.deepcopy(order)

    async def get(self, order_id: str) -> dict | None:
        return _copy(self.orders.get(order_id))

    async def update(self, order_id: str, fields: dict) -> dict | None:
        order = self.orders.get(order_id)
        if order is None:
            return None
        order.update(fields)
        return _copy(order)

    async def list_orders(
        self, email: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        items = list(self.orders.values())
        if email:
            needle = email.lower()
            items = [order for order in items if order["customerEmail"].lower() == needle]
        items.sort(key=lambda order: order["createdAt"], reverse=True)
        total = len(items)
        return [_copy(order) for order in items[skip : skip + limit]], total


class MongoOrderRepository:
    """MongoDB persistence owned exclusively by the order service."""

    def __init__(self, database: Any):
        self.orders = database["orders"]

    async def ensure_indexes(self) -> None:
        await self.orders.create_index("id", unique=True, name="order_id_unique")
        await self.orders.create_index("customerEmail", name="customer_email_idx")
        await self.orders.create_index("createdAt", name="created_at_idx")

    async def insert(self, order: dict) -> dict:
        await self.orders.insert_one(dict(order))
        return order

    async def get(self, order_id: str) -> dict | None:
        return _copy(await self.orders.find_one({"id": order_id}))

    async def update(self, order_id: str, fields: dict) -> dict | None:
        from pymongo import ReturnDocument

        updated = await self.orders.find_one_and_update(
            {"id": order_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def list_orders(
        self, email: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        query: dict = {}
        if email:
            query["customerEmail"] = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        total = await self.orders.count_documents(query)
        cursor = self.orders.find(query).sort("createdAt", -1).skip(skip).limit(limit)
        items = [_copy(document) async for document in cursor]
        return items, total
