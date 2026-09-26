"""Mocked product search — deterministic (query-seeded) so trajectories are
reproducible without any external API/billing dependency. Same interface a
real search backend would have, so swapping one in later is a one-file change."""

from __future__ import annotations

import random
import re
from typing import List, Optional

from agent.schemas import Product

_BRANDS = ["Lumen", "Everline", "NorthPeak", "UrbanCraft", "Solace", "Frame & Co", "Trailmark", "Homestead", "Vantage", "Cobalt"]
_ADJECTIVES = ["Classic", "Premium", "Compact", "Deluxe", "Everyday", "Studio", "Signature", "Modern"]
_PRICE_WORD_RE = re.compile(r"\b(under|below|over|around|about|budget|dollars?|usd|bucks?)\b", re.I)
_BUDGET_RE = re.compile(r"\$?\s?(\d{1,4})(?:\.\d{2})?\s?(?:dollars?|usd|bucks?)?", re.I)


def _clean_noun(query: str) -> str:
    q = _PRICE_WORD_RE.sub("", query)
    q = re.sub(r"\$?\d+(\.\d+)?", "", q)
    return " ".join(q.split()).strip().title() or "Item"


def _budget_hint(query: str) -> Optional[float]:
    m = _BUDGET_RE.search(query)
    return float(m.group(1)) if m else None


def product_search(query: str, num_results: int = 5) -> List[Product]:
    rng = random.Random(hash(query.lower()) & 0xFFFFFFFF)
    noun = _clean_noun(query)
    budget = _budget_hint(query)

    products: List[Product] = []
    for i in range(min(num_results, 5)):
        brand = rng.choice(_BRANDS)
        adj = rng.choice(_ADJECTIVES)
        price = round(rng.uniform(budget * 0.55, budget * 0.97), 2) if budget else round(rng.uniform(15, 250), 2)
        products.append(
            Product(
                product_id=f"mock-{abs(hash((query, i))) & 0xFFFF:x}",
                name=f"{brand} {adj} {noun}",
                price=price,
                url=None,
                snippet=f"{adj} {noun.lower()} by {brand} — well-rated for the price.",
            )
        )
    return products


PRODUCT_SEARCH_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "product_search",
        "description": "Search for products matching a query. Returns candidate products with name, price, and a short description.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise shopping query, e.g. 'wireless noise cancelling headphones under $150'",
                },
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
}
