"""Uniform API envelope used by every endpoint."""

from typing import Any

from pydantic import BaseModel


class SuccessResponse[T](BaseModel):
    success: bool = True
    data: T
    message: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody


def ok[T](data: T, message: str | None = None) -> SuccessResponse[T]:
    return SuccessResponse(data=data, message=message)
