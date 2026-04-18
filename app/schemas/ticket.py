from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TicketSource = Literal["email", "ticket_queue", "chat", "phone"]


class Ticket(BaseModel):
	model_config = ConfigDict(extra="forbid")

	ticket_id: str = Field(min_length=4)
	customer_email: str = Field(min_length=3)
	subject: str = Field(min_length=1)
	body: str = Field(min_length=1)
	source: TicketSource
	created_at: datetime
	tier: int = Field(ge=1, le=3)
	expected_action: str = Field(min_length=1)
