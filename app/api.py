from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.schemas import PlaceOrder
from app.service import OrderService

router = APIRouter()


def _service(request: Request) -> OrderService:
    return OrderService(request.app.state.repo, request.app.state.catalog)


@router.get("/health")
async def health(request: Request):
    return {"status": "up", "service": request.app.state.service_name}


@router.get("/ready")
async def ready(request: Request):
    mongo = getattr(request.app.state, "mongo", None)
    if mongo is not None:
        try:
            await mongo.admin.command("ping")
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "not-ready", "service": request.app.state.service_name},
            )
    return {"status": "ready", "service": request.app.state.service_name}


@router.post("/api/v1/orders", status_code=201)
async def place_order(body: PlaceOrder, request: Request):
    return await _service(request).place_order(body)


@router.get("/api/v1/orders")
async def list_orders(
    request: Request,
    customerEmail: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    return await _service(request).list_orders(customerEmail, page, pageSize)


@router.get("/api/v1/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    return await _service(request).get_order(order_id)


@router.post("/api/v1/orders/{order_id}/cancellations")
async def cancel_order(order_id: str, request: Request):
    return await _service(request).cancel_order(order_id)
