"""Mocked commerce tools. Deterministic (hash-seeded) so the same product_id
always yields the same stock/price behavior within a run, which keeps the
ideal-path judging sane instead of flaky."""

from __future__ import annotations

import random
from typing import Any, Dict, List

from agent.schemas import CartItem, CostSummary, DeliveryOption

_CART: Dict[str, List[CartItem]] = {}


def _seeded_rng(key: str) -> random.Random:
    return random.Random(hash(key) & 0xFFFFFFFF)


def check_inventory(product_id: str) -> Dict[str, Any]:
    rng = _seeded_rng(product_id)
    in_stock = rng.random() > 0.1
    return {
        "product_id": product_id,
        "in_stock": in_stock,
        "quantity_available": rng.randint(1, 40) if in_stock else 0,
    }


def add_to_cart(call_id: str, product_id: str, name: str, price: float, quantity: int = 1) -> Dict[str, Any]:
    _CART.setdefault(call_id, []).append(
        CartItem(product_id=product_id, name=name, price=price, quantity=quantity)
    )
    return {"status": "added", "cart_size": len(_CART[call_id])}


def shipping_estimate(zip_code: str, tier: str = "standard") -> Dict[str, Any]:
    rng = _seeded_rng(zip_code + tier)
    if tier == "expedited":
        option = DeliveryOption(tier="expedited", cost=round(rng.uniform(12, 25), 2), window="1-2 business days")
    else:
        option = DeliveryOption(tier="standard", cost=round(rng.uniform(0, 8), 2), window="4-7 business days")
    return option.model_dump()


def checkout(call_id: str, zip_code: str, tier: str = "standard") -> Dict[str, Any]:
    items = _CART.get(call_id, [])
    if not items:
        return {"error": "cart is empty"}
    subtotal = sum(i.price * i.quantity for i in items)
    ship = shipping_estimate(zip_code, tier)
    tax = round(subtotal * 0.08, 2)
    summary = CostSummary(
        line_items=items,
        subtotal=round(subtotal, 2),
        shipping_cost=ship["cost"],
        estimated_tax=tax,
        total=round(subtotal + ship["cost"] + tax, 2),
        delivery_window=ship["window"],
    )
    return summary.model_dump()


# Fixed fake order history — "we already have account details from the call"
# per the order-management flow, so no separate lookup/auth step is modeled.
_FAKE_ORDERS = [
    {"order_id": "ORD-1001", "item": "Wireless Headphones", "status": "shipped", "placed_on": "2026-09-01"},
    {"order_id": "ORD-1002", "item": "Standing Desk", "status": "processing", "placed_on": "2026-09-10"},
    {"order_id": "ORD-1003", "item": "Espresso Machine", "status": "delivered", "placed_on": "2026-08-20"},
]


def view_order_history(call_id: str) -> Dict[str, Any]:
    return {"orders": _FAKE_ORDERS}


def check_order(order_id: str) -> Dict[str, Any]:
    order = next((o for o in _FAKE_ORDERS if o["order_id"].lower() == order_id.lower()), None)
    if not order:
        return {"error": f"no order found with id {order_id}"}
    return order


def get_delivery_time(order_id: str) -> Dict[str, Any]:
    rng = _seeded_rng(order_id)
    days = rng.randint(1, 5)
    return {"order_id": order_id, "estimated_days": days, "window": f"{days}-{days + 2} business days"}


def cancel_order(order_id: str) -> Dict[str, Any]:
    return {"order_id": order_id, "status": "cancelled"}


def view_store_location(zip_code: str) -> Dict[str, Any]:
    """Deliberately always fails — a controlled, reproducible way to trigger a
    tool failure and observe how the agent (and the drift judge) handles it,
    without depending on a real flaky integration."""
    raise RuntimeError("Store locator service is temporarily unavailable")


def save_design(call_id: str, summary: str) -> Dict[str, Any]:
    return {"status": "saved", "summary": summary}


MOCK_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Check stock for a product.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a chosen product to the caller's cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                    "quantity": {"type": "integer", "default": 1},
                },
                "required": ["product_id", "name", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shipping_estimate",
            "description": "Get a shipping cost/window estimate for a zip code and tier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zip_code": {"type": "string"},
                    "tier": {"type": "string", "enum": ["standard", "expedited"], "default": "standard"},
                },
                "required": ["zip_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout",
            "description": "Finalize the order in the cart and get a cost summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zip_code": {"type": "string"},
                    "tier": {"type": "string", "enum": ["standard", "expedited"], "default": "standard"},
                },
                "required": ["zip_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_order_history",
            "description": "List the caller's past/current orders (account is already known from the call).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order",
            "description": "Look up the status of one specific order by id.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delivery_time",
            "description": "Get the delivery estimate for a specific order.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel a specific order.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_store_location",
            "description": "Look up the nearest physical store to a zip code.",
            "parameters": {
                "type": "object",
                "properties": {"zip_code": {"type": "string"}},
                "required": ["zip_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_design",
            "description": "Save the finalized design concept for the caller's space.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]
