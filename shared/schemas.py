from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok"]


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
