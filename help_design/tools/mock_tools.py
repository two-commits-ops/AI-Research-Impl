"""Mocked tools. None of this is DSPy — these are the deterministic,
non-language functions that TaskUIPlanner's ToolCallPlan gets dispatched to,
and that the (out-of-scope) capture loop's vision step reads from.

Kept as plain functions over fixture data so the compile step never needs
network access or a real search/vision/render backend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from help_design.fixtures.catalog import PALETTES, PRICE_RANGES, PRODUCTS, SHIPPING_RATES
from help_design.fixtures.frames import FRAMES
from help_design.schemas import (
    DeliveryOption,
    FrameFacts,
    Product,
    ToolCallPlan,
    ToolResults,
)


def product_search(query: str, filters: Optional[Dict[str, Any]] = None) -> List[Product]:
    """Very small keyword + tag/category filter over the mock catalog."""
    filters = filters or {}
    category = filters.get("category")
    tags = set(filters.get("tags", []))
    query_terms = set(query.lower().split())

    results = []
    for row in PRODUCTS:
        if category and row["category"] != category:
            continue
        if tags and not tags.intersection(row["tags"]):
            continue
        haystack = " ".join([row["name"], row["category"], *row["tags"]]).lower()
        if query_terms and not query_terms.intersection(haystack.split()):
            # keep it loose: any overlapping word counts as a match
            if not any(term in haystack for term in query_terms):
                continue
        results.append(Product(**row))
    return results


def price_range_lookup(category: str) -> Dict[str, float]:
    return dict(PRICE_RANGES.get(category, {"min": 0.0, "max": 0.0, "typical": 0.0}))


def color_palette_search(style_tags: List[str]) -> List[Dict[str, str]]:
    palette: List[Dict[str, str]] = []
    for tag in style_tags:
        palette.extend(PALETTES.get(tag, []))
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for swatch in palette:
        if swatch["name"] not in seen:
            seen.add(swatch["name"])
            deduped.append(swatch)
    return deduped or PALETTES.get("modern", [])


def vision_scene_tool(frame_id: str) -> FrameFacts:
    """Mocked vision-model output for one live-feed frame."""
    if frame_id not in FRAMES:
        raise KeyError(f"No mock fixture for frame_id={frame_id!r}")
    return FrameFacts(**FRAMES[frame_id])


def get_priced_products(product_ids: List[str]) -> List[Product]:
    """Look up full catalog records (incl. price) for a set of product ids —
    used to ground CostSynthesizer's `priced_items` from a DesignProposal's
    placements, the same way product_search grounds a Q&A task."""
    by_id = {row["product_id"]: row for row in PRODUCTS}
    return [Product(**by_id[pid]) for pid in product_ids if pid in by_id]


def shipping_options_lookup(location: str, product_ids: List[str]) -> List[DeliveryOption]:
    """Mocked shipping-tier quote: a flat base fee + a per-item fee, scaled
    by how many items are in the shopping list. `location` isn't actually
    geocoded here — a real implementation would vary cost by distance/zone;
    this only exists so the tool call is grounded in *something* real rather
    than a flat constant."""
    item_count = max(len(product_ids), 1)
    options = []
    for tier, rates in SHIPPING_RATES.items():
        cost = rates["base"] + rates["per_item"] * item_count
        options.append(DeliveryOption(tier=tier, cost=round(cost, 2), window=rates["window"]))
    return options


def dispatch_tool_call(plan: ToolCallPlan) -> ToolResults:
    """Routes a TaskUIPlanner-predicted ToolCallPlan to the right mock tool
    and normalizes the result into ToolResults, the shape
    AnswerOptionComposer expects regardless of which tool ran."""
    if plan.tool_name == "none":
        # Nothing to ground — the user's own answer (e.g. a shipping
        # address) *is* the data. Not a missing case, a legitimate one.
        return ToolResults()

    if plan.tool_name == "product_search":
        products = product_search(
            query=plan.tool_args.get("query", ""),
            filters=plan.tool_args.get("filters", {}),
        )
        return ToolResults(products=products)

    if plan.tool_name == "price_range_lookup":
        price_range = price_range_lookup(category=plan.tool_args.get("category", ""))
        return ToolResults(price_range=price_range)

    if plan.tool_name == "color_palette_search":
        palette = color_palette_search(style_tags=plan.tool_args.get("style_tags", []))
        return ToolResults(palette=palette)

    if plan.tool_name == "shipping_options_lookup":
        delivery_options = shipping_options_lookup(
            location=plan.tool_args.get("location", ""),
            product_ids=plan.tool_args.get("product_ids", []),
        )
        return ToolResults(delivery_options=delivery_options)

    raise ValueError(f"Unknown tool_name in ToolCallPlan: {plan.tool_name!r}")


def render_3d_scene(base_frames: List[FrameFacts], placements: List[Dict[str, Any]]):
    """Stage 5a stub. Deliberately NOT implemented here: 3D compositing/render
    is a non-DSPy runtime component, out of scope for the offline compile
    pass. Kept as a named stub only so the interface boundary is explicit."""
    raise NotImplementedError(
        "render_3d_scene is a runtime/non-DSPy component — build later."
    )


def add_to_cart(product_ids: List[str]) -> Dict[str, Any]:
    """Stage 6 (Finalize). Non-DSPy, deterministic — by the time this is
    callable, DesignProposal.placements already has the exact product ids,
    so there's no decision left to make; this just files the order. Mocked
    as a stub confirmation rather than a stubbed NotImplementedError, unlike
    render_3d_scene, because there's no real complexity being deferred here —
    a real implementation would just be a call to the store's cart API."""
    return {"cart_id": "cart_" + "_".join(product_ids)[:40], "item_count": len(product_ids)}
