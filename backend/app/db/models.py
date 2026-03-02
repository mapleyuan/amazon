from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Product:
    site: str
    asin: str
    title: str
    brand: str | None = None
    image_url: str | None = None
    detail_url: str | None = None
