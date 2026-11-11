from pydantic import BaseModel, ConfigDict, Field


class OrderItemIn(BaseModel):
    bookId: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=20)


class PlaceOrder(BaseModel):
    customerName: str = Field(min_length=2, max_length=80)
    customerEmail: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
    items: list[OrderItemIn] = Field(min_length=1, max_length=10)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customerName": "Ananya Shah",
                "customerEmail": "ananya.shah@example.com",
                "items": [{"bookId": "book-kitchen-orbits", "quantity": 1}],
            }
        }
    )
