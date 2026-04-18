from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrderStatus = Literal["processing", "shipped", "delivered", "cancelled"]
RefundStatus = Literal["refunded", "pending", "rejected"]


class Order(BaseModel):
	model_config = ConfigDict(extra="forbid")

	order_id: str = Field(min_length=4)
	customer_id: str = Field(min_length=2)
	product_id: str = Field(min_length=2)
	quantity: int = Field(ge=1)
	amount: float = Field(gt=0)
	status: OrderStatus
	order_date: date
	delivery_date: date | None = None
	return_deadline: date | None = None
	refund_status: RefundStatus | None = None
	notes: str = Field(min_length=1)
