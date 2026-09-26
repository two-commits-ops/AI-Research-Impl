"""Mock product catalog + price/palette tables backing the mocked tools.

Everything here is fixture data standing in for a real product/material
search backend. Kept small and hand-curated so grounding is easy to reason
about and to write metrics against.
"""

PRODUCTS = [
    # -- decking ---------------------------------------------------------
    {
        "product_id": "deck_composite_grey",
        "name": "Composite Grey Deck Boards",
        "category": "decking",
        "tags": ["modern", "low-maintenance", "grey", "composite"],
        "price": 8.50,
        "swatch_ref": "swatch_composite_grey",
    },
    {
        "product_id": "deck_cedar_natural",
        "name": "Natural Cedar Deck Boards",
        "category": "decking",
        "tags": ["traditional", "warm", "wood", "natural"],
        "price": 6.75,
        "swatch_ref": "swatch_cedar_natural",
    },
    {
        "product_id": "deck_tropical_hardwood",
        "name": "Tropical Hardwood Deck Boards",
        "category": "decking",
        "tags": ["premium", "durable", "rich-tone", "wood"],
        "price": 11.25,
        "swatch_ref": "swatch_tropical_hardwood",
    },
    # -- fencing -----------------------------------------------------------
    {
        "product_id": "fenc_horizontal_cedar",
        "name": "Horizontal Cedar Privacy Fence",
        "category": "fencing",
        "tags": ["modern", "wood", "privacy"],
        "price": 42.00,
        "swatch_ref": "swatch_horizontal_cedar",
    },
    {
        "product_id": "fenc_bamboo_screen",
        "name": "Rolled Bamboo Privacy Screen",
        "category": "fencing",
        "tags": ["minimalist", "natural", "privacy", "lightweight"],
        "price": 28.00,
        "swatch_ref": "swatch_bamboo_screen",
    },
    {
        "product_id": "fenc_composite_panel",
        "name": "Composite Privacy Panel",
        "category": "fencing",
        "tags": ["low-maintenance", "privacy", "modern"],
        "price": 55.00,
        "swatch_ref": "swatch_composite_panel",
    },
    # -- furniture -----------------------------------------------------------
    {
        "product_id": "furn_modern_sectional",
        "name": "Modern Outdoor Sectional",
        "category": "furniture",
        "tags": ["modern", "seating", "grey"],
        "price": 1450.00,
        "swatch_ref": "swatch_sectional_grey",
    },
    {
        "product_id": "furn_rustic_bench",
        "name": "Rustic Wood Bench",
        "category": "furniture",
        "tags": ["traditional", "seating", "wood"],
        "price": 380.00,
        "swatch_ref": "swatch_rustic_bench",
    },
    {
        "product_id": "furn_woven_lounge",
        "name": "Woven Lounge Chair Set",
        "category": "furniture",
        "tags": ["minimalist", "seating", "natural-fiber"],
        "price": 620.00,
        "swatch_ref": "swatch_woven_lounge",
    },
    # -- lighting -----------------------------------------------------------
    {
        "product_id": "light_string_warm",
        "name": "Warm String Lights",
        "category": "lighting",
        "tags": ["cozy", "ambient", "string"],
        "price": 45.00,
        "swatch_ref": None,
    },
    {
        "product_id": "light_path_modern",
        "name": "Modern Path Lights",
        "category": "lighting",
        "tags": ["modern", "path", "solar"],
        "price": 90.00,
        "swatch_ref": None,
    },
    # -- plants / greenery ----------------------------------------------------
    {
        "product_id": "plant_privacy_hedge",
        "name": "Privacy Hedge Screen Plants",
        "category": "plants",
        "tags": ["natural", "privacy", "greenery"],
        "price": 65.00,
        "swatch_ref": None,
    },
    {
        "product_id": "plant_ornamental_grass",
        "name": "Ornamental Grass Border",
        "category": "plants",
        "tags": ["natural", "low-maintenance", "greenery"],
        "price": 22.00,
        "swatch_ref": None,
    },
    # -- pool furniture ------------------------------------------------------
    {
        "product_id": "pool_lounger_modern",
        "name": "Modern Pool Lounger",
        "category": "pool_furniture",
        "tags": ["modern", "poolside", "weather-resistant"],
        "price": 320.00,
        "swatch_ref": "swatch_pool_lounger_modern",
    },
    {
        "product_id": "pool_lounger_classic",
        "name": "Classic Woven Pool Lounger",
        "category": "pool_furniture",
        "tags": ["traditional", "poolside", "woven"],
        "price": 260.00,
        "swatch_ref": "swatch_pool_lounger_classic",
    },
    # -- shade / cover structures ---------------------------------------------
    {
        "product_id": "freestanding_pergola",
        "name": "Freestanding Aluminum Pergola",
        "category": "structures",
        "tags": ["modern", "shade", "freestanding"],
        "price": 2800.00,
        "swatch_ref": None,
    },
    {
        "product_id": "pergola_attached",
        "name": "Wall-Mounted Attached Pergola",
        "category": "structures",
        "tags": ["modern", "shade", "attached"],
        "price": 3400.00,
        "swatch_ref": None,
    },
    {
        "product_id": "shade_sail_standard",
        "name": "Triangular Shade Sail",
        "category": "structures",
        "tags": ["modern", "shade", "lightweight"],
        "price": 220.00,
        "swatch_ref": None,
    },
    {
        "product_id": "retractable_awning",
        "name": "Retractable Patio Awning",
        "category": "structures",
        "tags": ["modern", "shade", "retractable"],
        "price": 1800.00,
        "swatch_ref": None,
    },
    # -- garden beds -----------------------------------------------------------
    {
        "product_id": "raised_bed_cedar",
        "name": "Cedar Raised Garden Bed Kit",
        "category": "garden_beds",
        "tags": ["natural", "modular", "wood"],
        "price": 145.00,
        "swatch_ref": "swatch_raised_bed_cedar",
    },
    {
        "product_id": "raised_bed_composite",
        "name": "Composite Raised Garden Bed Kit",
        "category": "garden_beds",
        "tags": ["modern", "modular", "low-maintenance"],
        "price": 180.00,
        "swatch_ref": "swatch_raised_bed_composite",
    },
    # -- irrigation -----------------------------------------------------------
    {
        "product_id": "irrigation_drip_kit",
        "name": "Drip Irrigation Starter Kit",
        "category": "irrigation",
        "tags": ["efficient", "low-water", "DIY"],
        "price": 95.00,
        "swatch_ref": None,
    },
    {
        "product_id": "irrigation_soaker_kit",
        "name": "Soaker Hose Kit",
        "category": "irrigation",
        "tags": ["simple", "budget", "DIY"],
        "price": 55.00,
        "swatch_ref": None,
    },
    # -- turf -----------------------------------------------------------------
    {
        "product_id": "turf_synthetic_dog",
        "name": "Pet-Friendly Synthetic Turf",
        "category": "turf",
        "tags": ["durable", "easy-clean", "pet-friendly"],
        "price": 4.75,
        "swatch_ref": "swatch_turf_dog",
    },
    {
        "product_id": "turf_standard",
        "name": "Standard Synthetic Turf",
        "category": "turf",
        "tags": ["durable", "low-maintenance"],
        "price": 3.90,
        "swatch_ref": "swatch_turf_standard",
    },
    # -- low-water / xeriscape plants ------------------------------------------
    {
        "product_id": "plant_xeriscape_mix",
        "name": "Xeriscape Planting Mix",
        "category": "low_water_plants",
        "tags": ["desert-modern", "drought-tolerant", "low-water"],
        "price": 18.00,
        "swatch_ref": "swatch_xeriscape_mix",
    },
    {
        "product_id": "plant_succulent_border",
        "name": "Succulent Border Mix",
        "category": "low_water_plants",
        "tags": ["desert-modern", "drought-tolerant", "low-water"],
        "price": 24.00,
        "swatch_ref": "swatch_succulent_border",
    },
    # -- outdoor kitchen --------------------------------------------------------
    {
        "product_id": "counter_concrete_outdoor",
        "name": "Poured Concrete Outdoor Counter",
        "category": "kitchen_outdoor",
        "tags": ["modern", "durable", "counter"],
        "price": 1200.00,
        "swatch_ref": "swatch_counter_concrete",
    },
    {
        "product_id": "counter_stone_outdoor",
        "name": "Natural Stone Outdoor Counter",
        "category": "kitchen_outdoor",
        "tags": ["natural", "premium", "counter"],
        "price": 1800.00,
        "swatch_ref": "swatch_counter_stone",
    },
    # -- safety surfacing --------------------------------------------------------
    {
        "product_id": "surfacing_rubber_mulch",
        "name": "Impact-Safe Rubber Mulch",
        "category": "surfacing",
        "tags": ["family-friendly", "safe", "impact-absorbing"],
        "price": 3.25,
        "swatch_ref": "swatch_rubber_mulch",
    },
    {
        "product_id": "surfacing_engineered_wood",
        "name": "Engineered Wood Fiber Surfacing",
        "category": "surfacing",
        "tags": ["natural", "family-friendly", "budget"],
        "price": 2.10,
        "swatch_ref": "swatch_engineered_wood_fiber",
    },
    # -- play structures --------------------------------------------------------
    {
        "product_id": "play_structure_combo",
        "name": "Climbing + Swing Set Combo",
        "category": "play_structures",
        "tags": ["family-friendly", "active-play", "wood-frame"],
        "price": 1650.00,
        "swatch_ref": None,
    },
    {
        "product_id": "play_structure_swing_only",
        "name": "Classic Swing Set",
        "category": "play_structures",
        "tags": ["family-friendly", "simple"],
        "price": 650.00,
        "swatch_ref": None,
    },
]

SUPPORTED_CATEGORIES = [
    "materials",
    "furniture",
    "plants",
    "structures",
    "lighting",
    "irrigation",
    "color",
    "budget",
    "logistics",
]
"""Task topic_areas / EditTaskList grounding categories this mocked backend
can actually back with real options. TaskListPlanner and TaskListEditor are
both instructed to only add/keep tasks that map to one of these — anything
else (a swimming pool, a hot tub, ...) gets declined rather than invented.
'logistics' backs the auto-appended Shipping & Timing task — it isn't
something TaskListPlanner would propose up front, but it's listed here so
TaskListEditor recognizes it as already-groundable if a user asks about
shipping early."""

PRICE_RANGES = {
    "decking_project": {"min": 2000.0, "max": 15000.0, "typical": 6000.0},
    "fencing_project": {"min": 1000.0, "max": 8000.0, "typical": 3000.0},
    "furniture": {"min": 300.0, "max": 3000.0, "typical": 900.0},
    "lighting_project": {"min": 100.0, "max": 1200.0, "typical": 400.0},
    "pool_area_project": {"min": 2000.0, "max": 12000.0, "typical": 5000.0},
    "garden_project": {"min": 200.0, "max": 2000.0, "typical": 800.0},
    "turf_project": {"min": 500.0, "max": 5000.0, "typical": 1500.0},
    "landscaping_project": {"min": 1500.0, "max": 10000.0, "typical": 4000.0},
    "patio_cover_project": {"min": 3000.0, "max": 15000.0, "typical": 7000.0},
    "play_area_project": {"min": 800.0, "max": 6000.0, "typical": 2500.0},
}

SHIPPING_RATES = {
    "standard": {"base": 25.0, "per_item": 5.0, "window": "5-7 business days"},
    "expedited": {"base": 55.0, "per_item": 8.0, "window": "2-3 business days"},
}

PALETTES = {
    "minimalist": [
        {"name": "Driftwood Grey", "hex": "#A8A296"},
        {"name": "Charcoal", "hex": "#3A3A3A"},
        {"name": "Natural Tan", "hex": "#D8C4A0"},
    ],
    "traditional": [
        {"name": "Warm Cedar", "hex": "#9C6B4A"},
        {"name": "Forest Green", "hex": "#3F5B3E"},
        {"name": "Cream", "hex": "#F1E9DA"},
    ],
    "modern": [
        {"name": "Slate Grey", "hex": "#5C6670"},
        {"name": "Matte Black", "hex": "#22252A"},
        {"name": "Soft White", "hex": "#EDEDED"},
    ],
    "desert-modern": [
        {"name": "Warm Sand", "hex": "#D9B88F"},
        {"name": "Terracotta", "hex": "#C1653B"},
        {"name": "Sage Green", "hex": "#9CAF88"},
    ],
}
