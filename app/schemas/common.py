from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total_elements: int
    total_pages: int
