"""Hand-authored mocked end-to-end sessions.

These are the ground truth this whole compile step trains/evaluates against.
Two full backyard sessions (deck refresh, privacy fence) give topic diversity
across materials / budget / furniture / color question types, which is what
TaskUIPlanner needs to learn the tool <-> widget mapping instead of
memorizing one example. A couple of standalone queries add brief-extraction
diversity beyond "backyard".

Plain dicts here, on purpose — fixtures/trainsets.py is the only place that
turns these into pydantic objects / dspy.Examples, so this file stays easy to
read and extend by hand.
"""

SESSION_A = {
    "session_id": "session_a_deck_refresh",
    "capture_mode": "video",
    "raw_query": (
        "Hey i need to redesign my backyard, the deck is looking pretty worn "
        "out and I want it to feel more inviting."
    ),
    "task_list": [
        {"task_name": "Decking Materials", "topic_area": "materials"},
        {"task_name": "Budget", "topic_area": "budget"},
        {"task_name": "Furniture", "topic_area": "furniture"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": [
            "refresh the worn-out deck",
            "make the space feel more inviting",
        ],
        "constraints": [],
        "missing_info": ["budget", "material preference", "furniture style"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_a1",
            "gold_is_complete": False,
            "gold_missing_elements": ["fence line"],
            "gold_adjustment_instruction": "Pan left about a foot to bring the fence line into frame.",
        },
        {
            "frame_id": "frame_a2",
            "gold_is_complete": False,
            "gold_missing_elements": ["deck-to-grass transition"],
            "gold_adjustment_instruction": "Tilt down slightly to show where the deck meets the lawn.",
        },
        {
            "frame_id": "frame_a3",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["traditional", "worn wood"],
        "key_features": [
            "existing wood deck",
            "wood fence",
            "lawn area",
            "sliding door access",
        ],
        "condition_notes": ["deck boards appear faded and worn"],
        "opportunities": [
            "replace decking material",
            "add a defined seating area",
            "improve evening lighting",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What type of decking material are you drawn to?",
            "topic": "materials",
            "draft_options": [
                "Composite grey boards",
                "Natural cedar wood",
                "Tropical hardwood",
            ],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {"query": "decking", "filters": {"category": "decking"}},
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "deck_composite_grey",
            "chosen_answer": "Composite Grey Deck Boards",
            "task_name": "Decking Materials",
        },
        {
            "question_text": "What's your budget range for this deck project?",
            "topic": "budget",
            "draft_options": ["Under $3,000", "$3,000-$8,000", "$8,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "decking_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "6000",
            "task_name": "Budget",
        },
        {
            "question_text": "Which furniture style feels right for the new seating area?",
            "topic": "furniture_style",
            "draft_options": [
                "Modern sectional",
                "Rustic wood bench",
                "Woven lounge chairs",
            ],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "furniture seating",
                    "filters": {"category": "furniture"},
                },
            },
            "ui_component_type": "image_carousel",
            "chosen_product_id": "furn_woven_lounge",
            "chosen_answer": "Woven Lounge Chair Set",
            "task_name": "Furniture",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A refreshed, low-maintenance deck built around composite grey "
            "boards, anchored by a woven lounge seating area near the "
            "sliding door so the space reads as an intentional outdoor "
            "living room rather than an afterthought."
        ),
        "layout_notes": (
            "Replace the full existing deck footprint with the new "
            "composite boards. Place the woven lounge chairs in the corner "
            "near the sliding door, facing out toward the lawn."
        ),
        "shopping_list": ["Composite Grey Deck Boards", "Woven Lounge Chair Set"],
        "next_steps": [
            "Confirm final deck measurements before ordering boards",
            "Get an installer quote for board replacement",
            "Order the woven lounge set to arrive after installation",
        ],
        "placements": [
            {
                "product_id": "deck_composite_grey",
                "zone": "full deck footprint",
                "position_hint": "replace existing worn boards edge to edge",
            },
            {
                "product_id": "furn_woven_lounge",
                "zone": "deck corner near sliding door",
                "position_hint": "arrange facing the lawn",
            },
        ],
    },
    # Auto-appended once DesignSynthesizer finishes — fills the 3D-render
    # wait with delivery grounding, not part of the user-editable task_list.
    "logistics": {"shipping_location": "98105", "delivery_tier": "standard"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "98105",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "98105",
                    "product_ids": ["deck_composite_grey", "furn_woven_lounge"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "standard",
            "chosen_answer": "Standard",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_B = {
    "session_id": "session_b_privacy_fence",
    "capture_mode": "video",
    "raw_query": (
        "I want more privacy in my backyard — my neighbors can see right "
        "into my yard from their upstairs windows."
    ),
    "task_list": [
        {"task_name": "Fencing Materials", "topic_area": "materials"},
        {"task_name": "Budget", "topic_area": "budget"},
        {"task_name": "Color Palette", "topic_area": "color"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": ["increase privacy from neighboring sightlines"],
        "constraints": ["keep the existing patio"],
        "missing_info": ["fence height/material preference", "budget", "color/style preference"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_b1",
            "gold_is_complete": False,
            "gold_missing_elements": ["full fence line", "neighboring sightline"],
            "gold_adjustment_instruction": "Pan right to bring the rest of the fence line into frame.",
        },
        {
            "frame_id": "frame_b2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["minimalist"],
        "key_features": ["existing patio", "garden bed", "low wood fence"],
        "condition_notes": ["current fence is low, sightline exposed"],
        "opportunities": [
            "increase fence height or add screening",
            "add privacy plants along the fence line",
            "introduce a cohesive minimalist palette",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What kind of privacy screening material do you like?",
            "topic": "materials",
            "draft_options": [
                "Horizontal cedar fence",
                "Bamboo screen",
                "Composite privacy panel",
            ],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "privacy fencing screen",
                    "filters": {"category": "fencing"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "fenc_bamboo_screen",
            "chosen_answer": "Rolled Bamboo Privacy Screen",
            "task_name": "Fencing Materials",
        },
        {
            "question_text": "What's your budget range for the privacy upgrade?",
            "topic": "budget",
            "draft_options": ["Under $1,500", "$1,500-$4,000", "$4,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "fencing_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "3000",
            "task_name": "Budget",
        },
        {
            "question_text": "Any color palette you're drawn to for the new screening?",
            "topic": "color",
            "draft_options": ["Natural tan", "Charcoal", "Driftwood grey"],
            "tool_call_plan": {
                "tool_name": "color_palette_search",
                "tool_args": {"style_tags": ["minimalist"]},
            },
            "ui_component_type": "color_picker",
            "chosen_product_id": None,
            "chosen_answer": "Driftwood Grey",
            "task_name": "Color Palette",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A minimalist bamboo privacy screen raised along the existing "
            "fence line, finished in a driftwood grey palette so the "
            "upgrade reads as a deliberate design choice, not just a taller "
            "fence."
        ),
        "layout_notes": (
            "Mount the bamboo screening along the full existing fence line "
            "to close off the upstairs sightline, keeping the current "
            "patio and garden bed untouched."
        ),
        "shopping_list": ["Rolled Bamboo Privacy Screen"],
        "next_steps": [
            "Measure the full fence run for screen panel quantity",
            "Confirm mounting hardware compatible with the existing fence",
            "Order screening in the driftwood grey finish",
        ],
        "placements": [
            {
                "product_id": "fenc_bamboo_screen",
                "zone": "full existing fence line",
                "position_hint": "mount along the top to add height and close the sightline",
            }
        ],
    },
    "logistics": {"shipping_location": "60614", "delivery_tier": "standard"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "60614",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {"location": "60614", "product_ids": ["fenc_bamboo_screen"]},
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "standard",
            "chosen_answer": "Standard",
            "task_name": "Shipping & Timing",
        },
    ],
}
SESSION_C = {
    "session_id": "session_c_pool_area",
    "capture_mode": "video",
    "raw_query": (
        "I want to modernize the area around our pool, it feels dated and "
        "the lounge chairs are falling apart."
    ),
    "task_list": [
        {"task_name": "Furniture", "topic_area": "furniture"},
        {"task_name": "Shade Structure", "topic_area": "structures"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": [
            "modernize the pool area",
            "replace worn lounge furniture",
        ],
        "constraints": [],
        "missing_info": ["budget", "furniture style", "shade preference"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_c1",
            "gold_is_complete": False,
            "gold_missing_elements": ["far end of pool"],
            "gold_adjustment_instruction": "Pan right to bring the far end of the pool into frame.",
        },
        {
            "frame_id": "frame_c2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["dated", "poolside"],
        "key_features": ["in-ground pool", "concrete pool deck", "old lounge chairs"],
        "condition_notes": ["lounge furniture is worn and mismatched"],
        "opportunities": [
            "replace poolside furniture",
            "add shade structure",
            "update deck lighting",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What style of pool lounger are you drawn to?",
            "topic": "furniture_style",
            "draft_options": ["Modern lounger", "Classic woven lounger"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "pool lounger",
                    "filters": {"category": "pool_furniture"},
                },
            },
            "ui_component_type": "image_carousel",
            "chosen_product_id": "pool_lounger_modern",
            "chosen_answer": "Modern Pool Lounger",
            "task_name": "Furniture",
        },
        {
            "question_text": "Do you want the new shade structure attached to the house or freestanding?",
            "topic": "shade_structure",
            "draft_options": ["Attached pergola", "Freestanding pergola", "Shade sail"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "shade structure",
                    "filters": {"category": "structures"},
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "freestanding_pergola",
            "chosen_answer": "Freestanding Aluminum Pergola",
            "task_name": "Shade Structure",
        },
        {
            "question_text": "What's your budget range for the pool area refresh?",
            "topic": "budget",
            "draft_options": ["Under $3,000", "$3,000-$8,000", "$8,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "pool_area_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "5000",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A modernized poolside built around new loungers and a "
            "freestanding pergola for shade, turning a dated deck into a "
            "clean, resort-style hangout."
        ),
        "layout_notes": (
            "Place the modern loungers along the sunny side of the pool "
            "deck. Position the freestanding pergola over the seating "
            "cluster at the far end for midday shade."
        ),
        "shopping_list": ["Modern Pool Lounger", "Freestanding Aluminum Pergola"],
        "next_steps": [
            "Confirm pool deck load capacity for the pergola footings",
            "Order loungers to match the pergola's install timeline",
            "Get a quote for deck lighting as a follow-on phase",
        ],
        "placements": [
            {
                "product_id": "pool_lounger_modern",
                "zone": "sunny side of pool deck",
                "position_hint": "line up facing the pool",
            },
            {
                "product_id": "freestanding_pergola",
                "zone": "far end of pool deck",
                "position_hint": "center over the lounger cluster",
            },
        ],
    },
    "logistics": {"shipping_location": "85251", "delivery_tier": "expedited"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "85251",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "85251",
                    "product_ids": ["pool_lounger_modern", "freestanding_pergola"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "expedited",
            "chosen_answer": "Expedited",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_D = {
    "session_id": "session_d_vegetable_garden",
    "capture_mode": "photo",
    "raw_query": (
        "I want to expand our vegetable garden bed and make watering "
        "easier, we're tired of dragging the hose around."
    ),
    "task_list": [
        {"task_name": "Garden Bed Materials", "topic_area": "materials"},
        {"task_name": "Irrigation", "topic_area": "irrigation"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": [
            "expand the vegetable garden bed",
            "simplify watering",
        ],
        "constraints": ["keep it low cost"],
        "missing_info": ["bed material", "irrigation type", "layout size"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_d1",
            "gold_is_complete": False,
            "gold_missing_elements": ["left half of existing bed"],
            "gold_adjustment_instruction": "Please upload another photo that also shows the left half of the existing bed.",
        },
        {
            "frame_id": "frame_d2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["utilitarian", "garden"],
        "key_features": ["existing raised bed", "garden hose reel", "fence border"],
        "condition_notes": ["current bed is small and irrigation is manual"],
        "opportunities": [
            "add raised bed modules",
            "install drip irrigation",
            "improve pathway between beds",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What raised bed material do you like?",
            "topic": "materials",
            "draft_options": ["Cedar wood", "Composite"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "raised garden bed",
                    "filters": {"category": "garden_beds"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "raised_bed_cedar",
            "chosen_answer": "Cedar Raised Garden Bed Kit",
            "task_name": "Garden Bed Materials",
        },
        {
            "question_text": "Do you want drip irrigation or a soaker hose system?",
            "topic": "irrigation_type",
            "draft_options": ["Drip irrigation kit", "Soaker hose kit"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "irrigation",
                    "filters": {"category": "irrigation"},
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "irrigation_drip_kit",
            "chosen_answer": "Drip Irrigation Starter Kit",
            "task_name": "Irrigation",
        },
        {
            "question_text": "What's your budget range for the garden expansion?",
            "topic": "budget",
            "draft_options": ["Under $500", "$500-$1,200", "$1,200+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "garden_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "800",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "An expanded cedar raised-bed garden fed by a drip irrigation "
            "kit, so watering becomes a five-minute check instead of a "
            "daily chore."
        ),
        "layout_notes": (
            "Extend the existing bed footprint with matching cedar "
            "modules, and run drip irrigation lines to every module before "
            "backfilling with soil."
        ),
        "shopping_list": ["Cedar Raised Garden Bed Kit", "Drip Irrigation Starter Kit"],
        "next_steps": [
            "Measure the full expansion footprint against the fence border",
            "Order bed modules and irrigation kit together",
            "Plan planting layout once beds are installed",
        ],
        "placements": [
            {
                "product_id": "raised_bed_cedar",
                "zone": "expanded bed footprint",
                "position_hint": "extend from the existing bed toward the fence",
            },
            {
                "product_id": "irrigation_drip_kit",
                "zone": "all bed modules",
                "position_hint": "run lines to each module from the hose reel",
            },
        ],
    },
    "logistics": {"shipping_location": "97201", "delivery_tier": "standard"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "97201",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "97201",
                    "product_ids": ["raised_bed_cedar", "irrigation_drip_kit"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "standard",
            "chosen_answer": "Standard",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_E = {
    "session_id": "session_e_dog_run",
    "capture_mode": "video",
    "raw_query": (
        "Our dog destroys the side yard, we want to turn it into a proper "
        "dog run that's easy to clean."
    ),
    "task_list": [
        {"task_name": "Turf Materials", "topic_area": "materials"},
        {"task_name": "Shade Structure", "topic_area": "structures"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "side yard",
        "stated_goals": [
            "create a durable dog run",
            "make cleanup easy",
        ],
        "constraints": [],
        "missing_info": ["surfacing type", "shade needs", "budget"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_e1",
            "gold_is_complete": False,
            "gold_missing_elements": ["far fence corner"],
            "gold_adjustment_instruction": "Pan forward to bring the far fence corner into frame.",
        },
        {
            "frame_id": "frame_e2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["utilitarian"],
        "key_features": ["narrow side yard", "existing wood fence", "patchy grass"],
        "condition_notes": ["grass is torn up and muddy in spots"],
        "opportunities": [
            "install synthetic turf",
            "add shade coverage",
            "reinforce fence corner",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What surfacing do you want for the dog run?",
            "topic": "materials",
            "draft_options": ["Pet-friendly synthetic turf", "Standard synthetic turf"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "turf surfacing",
                    "filters": {"category": "turf"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "turf_synthetic_dog",
            "chosen_answer": "Pet-Friendly Synthetic Turf",
            "task_name": "Turf Materials",
        },
        {
            "question_text": "Would you like added shade coverage over the run?",
            "topic": "shade_structure",
            "draft_options": ["Shade sail", "No shade for now"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "shade sail",
                    "filters": {"category": "structures"},
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "shade_sail_standard",
            "chosen_answer": "Triangular Shade Sail",
            "task_name": "Shade Structure",
        },
        {
            "question_text": "What's your budget range for the dog run upgrade?",
            "topic": "budget",
            "draft_options": ["Under $800", "$800-$2,000", "$2,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "turf_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "1500",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A pet-friendly synthetic turf run shaded by a triangular "
            "shade sail, built to survive a dog's daily wear while staying "
            "easy to hose down."
        ),
        "layout_notes": (
            "Lay turf across the full side yard run, corner to corner. "
            "Anchor the shade sail over the section nearest the house for "
            "midday relief."
        ),
        "shopping_list": ["Pet-Friendly Synthetic Turf", "Triangular Shade Sail"],
        "next_steps": [
            "Confirm drainage before turf installation",
            "Order turf sized to the full run measurement",
            "Install shade sail anchors into fence posts",
        ],
        "placements": [
            {
                "product_id": "turf_synthetic_dog",
                "zone": "full side yard run",
                "position_hint": "corner to corner replacement of existing grass",
            },
            {
                "product_id": "shade_sail_standard",
                "zone": "section nearest the house",
                "position_hint": "anchor between fence posts overhead",
            },
        ],
    },
    "logistics": {"shipping_location": "78704", "delivery_tier": "expedited"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "78704",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "78704",
                    "product_ids": ["turf_synthetic_dog", "shade_sail_standard"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "expedited",
            "chosen_answer": "Expedited",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_F = {
    "session_id": "session_f_front_yard_curb_appeal",
    "capture_mode": "photo",
    "raw_query": (
        "Our front yard needs better curb appeal and we want to cut down "
        "on watering."
    ),
    "task_list": [
        {"task_name": "Planting", "topic_area": "plants"},
        {"task_name": "Color Palette", "topic_area": "color"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "front yard",
        "stated_goals": [
            "improve curb appeal",
            "reduce water usage",
        ],
        "constraints": [],
        "missing_info": ["plant style", "budget", "hardscape preference"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_f1",
            "gold_is_complete": False,
            "gold_missing_elements": ["driveway edge"],
            "gold_adjustment_instruction": "Please upload another photo that includes the driveway-side edge of the yard.",
        },
        {
            "frame_id": "frame_f2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["desert-modern"],
        "key_features": ["lawn strip", "front walkway", "bare planting beds"],
        "condition_notes": ["lawn is patchy and water-hungry"],
        "opportunities": [
            "replace lawn with drought-tolerant plants",
            "add gravel/hardscape accents",
            "update path lighting",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "Which low-water planting style appeals to you?",
            "topic": "materials",
            "draft_options": ["Xeriscape mix", "Succulent border"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "low water plants",
                    "filters": {"category": "low_water_plants"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "plant_xeriscape_mix",
            "chosen_answer": "Xeriscape Planting Mix",
            "task_name": "Planting",
        },
        {
            "question_text": "Any color palette preference for the hardscape gravel?",
            "topic": "color",
            "draft_options": ["Warm sand", "Terracotta", "Sage green"],
            "tool_call_plan": {
                "tool_name": "color_palette_search",
                "tool_args": {"style_tags": ["desert-modern"]},
            },
            "ui_component_type": "color_picker",
            "chosen_product_id": None,
            "chosen_answer": "Warm Sand",
            "task_name": "Color Palette",
        },
        {
            "question_text": "What's your budget range for the front yard refresh?",
            "topic": "budget",
            "draft_options": ["Under $2,000", "$2,000-$6,000", "$6,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "landscaping_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "4000",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A drought-tolerant front yard built around a xeriscape "
            "planting mix and warm sand-toned gravel, trading the "
            "water-hungry lawn for low-maintenance curb appeal."
        ),
        "layout_notes": (
            "Replace the lawn strip with the xeriscape mix, bordered by "
            "warm sand gravel along the front walkway and driveway edge."
        ),
        "shopping_list": ["Xeriscape Planting Mix"],
        "next_steps": [
            "Remove existing lawn strip before planting",
            "Order gravel in the warm sand tone for hardscape borders",
            "Add path lighting as a follow-on phase",
        ],
        "placements": [
            {
                "product_id": "plant_xeriscape_mix",
                "zone": "full lawn strip",
                "position_hint": "replace lawn edge to edge along the walkway",
            }
        ],
    },
    "logistics": {"shipping_location": "85018", "delivery_tier": "standard"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "85018",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {"location": "85018", "product_ids": ["plant_xeriscape_mix"]},
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "standard",
            "chosen_answer": "Standard",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_G = {
    "session_id": "session_g_covered_patio",
    "capture_mode": "video",
    "raw_query": (
        "We want to add a covered patio with space to eventually put in "
        "an outdoor kitchen."
    ),
    "task_list": [
        {"task_name": "Shade Structure", "topic_area": "structures"},
        {"task_name": "Kitchen Counter Materials", "topic_area": "materials"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": [
            "add a covered patio",
            "leave room for a future outdoor kitchen",
        ],
        "constraints": ["phase 1 is just the patio cover"],
        "missing_info": ["cover style", "budget", "material for the counter prep area"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_g1",
            "gold_is_complete": False,
            "gold_missing_elements": ["roofline where cover would attach"],
            "gold_adjustment_instruction": "Tilt up to bring the roofline into frame.",
        },
        {
            "frame_id": "frame_g2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["modern", "entertaining"],
        "key_features": ["concrete patio slab", "back wall of house", "open sky above patio"],
        "condition_notes": ["patio currently has no shade coverage"],
        "opportunities": [
            "add a pergola or solid patio cover",
            "rough in space for a future kitchen counter",
            "add ambient lighting for evenings",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "Do you want the patio cover attached to the house or freestanding?",
            "topic": "shade_structure",
            "draft_options": ["Attached pergola", "Freestanding pergola", "Retractable awning"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "patio cover pergola",
                    "filters": {"category": "structures"},
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "pergola_attached",
            "chosen_answer": "Wall-Mounted Attached Pergola",
            "task_name": "Shade Structure",
        },
        {
            "question_text": "What countertop material would you want for the future outdoor kitchen prep area?",
            "topic": "materials",
            "draft_options": ["Poured concrete", "Natural stone"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "outdoor kitchen counter",
                    "filters": {"category": "kitchen_outdoor"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "counter_concrete_outdoor",
            "chosen_answer": "Poured Concrete Outdoor Counter",
            "task_name": "Kitchen Counter Materials",
        },
        {
            "question_text": "What's your budget range for phase 1 (the patio cover)?",
            "topic": "budget",
            "draft_options": ["Under $5,000", "$5,000-$10,000", "$10,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "patio_cover_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "7000",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "An attached pergola covering the full patio slab now, with a "
            "poured concrete counter zone roughed in along the back wall "
            "so the outdoor kitchen can drop in as phase 2."
        ),
        "layout_notes": (
            "Mount the pergola off the back wall to cover the full patio "
            "slab. Reserve a run along the wall for the future concrete "
            "counter, keeping it clear in phase 1."
        ),
        "shopping_list": ["Wall-Mounted Attached Pergola", "Poured Concrete Outdoor Counter"],
        "next_steps": [
            "Confirm wall attachment points can bear the pergola load",
            "Order the pergola for phase 1 installation",
            "Rough in electrical/plumbing stubs for the phase 2 counter",
        ],
        "placements": [
            {
                "product_id": "pergola_attached",
                "zone": "full patio slab",
                "position_hint": "mount to the back wall of the house",
            },
            {
                "product_id": "counter_concrete_outdoor",
                "zone": "back wall counter run",
                "position_hint": "reserve space now, install in phase 2",
            },
        ],
    },
    "logistics": {"shipping_location": "94110", "delivery_tier": "expedited"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "94110",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "94110",
                    "product_ids": ["pergola_attached", "counter_concrete_outdoor"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "expedited",
            "chosen_answer": "Expedited",
            "task_name": "Shipping & Timing",
        },
    ],
}

SESSION_H = {
    "session_id": "session_h_kids_play_area",
    "capture_mode": "photo",
    "raw_query": (
        "We want to set up a safe play area for our kids in the backyard, "
        "something with shade."
    ),
    "task_list": [
        {"task_name": "Safety Surfacing", "topic_area": "materials"},
        {"task_name": "Play Structure", "topic_area": "structures"},
        {"task_name": "Budget", "topic_area": "budget"},
    ],
    "brief": {
        "space_type": "backyard",
        "stated_goals": [
            "create a safe kids play area",
            "include shade",
        ],
        "constraints": ["needs to be safe for a toddler and a 6-year-old"],
        "missing_info": ["surfacing type", "structure type", "budget"],
    },
    "frame_sequence": [
        {
            "frame_id": "frame_h1",
            "gold_is_complete": False,
            "gold_missing_elements": ["tree canopy"],
            "gold_adjustment_instruction": "Please upload another photo that includes the tree canopy above.",
        },
        {
            "frame_id": "frame_h2",
            "gold_is_complete": True,
            "gold_missing_elements": [],
            "gold_adjustment_instruction": None,
        },
    ],
    "scene_summary": {
        "style_tags": ["family-friendly"],
        "key_features": ["open lawn area", "existing tree", "bare soil patch"],
        "condition_notes": ["no dedicated play surface currently"],
        "opportunities": [
            "add impact-safe surfacing",
            "install a shade-friendly play structure",
            "define play area boundary",
        ],
    },
    "qa_exchanges": [
        {
            "question_text": "What kind of safety surfacing do you want under the play area?",
            "topic": "materials",
            "draft_options": ["Rubber mulch", "Engineered wood fiber"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "play surfacing rubber mulch",
                    "filters": {"category": "surfacing"},
                },
            },
            "ui_component_type": "swatch_grid",
            "chosen_product_id": "surfacing_rubber_mulch",
            "chosen_answer": "Impact-Safe Rubber Mulch",
            "task_name": "Safety Surfacing",
        },
        {
            "question_text": "Do you want a swing set, a climbing structure, or both?",
            "topic": "structure_type",
            "draft_options": ["Combo climbing + swing set", "Swing set only"],
            "tool_call_plan": {
                "tool_name": "product_search",
                "tool_args": {
                    "query": "play structure",
                    "filters": {"category": "play_structures"},
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "play_structure_combo",
            "chosen_answer": "Climbing + Swing Set Combo",
            "task_name": "Play Structure",
        },
        {
            "question_text": "What's your budget range for the play area?",
            "topic": "budget",
            "draft_options": ["Under $1,500", "$1,500-$4,000", "$4,000+"],
            "tool_call_plan": {
                "tool_name": "price_range_lookup",
                "tool_args": {"category": "play_area_project"},
            },
            "ui_component_type": "slider",
            "chosen_product_id": None,
            "chosen_answer": "2500",
            "task_name": "Budget",
        },
    ],
    "design_proposal": {
        "concept_narrative": (
            "A shaded play zone anchored by impact-safe rubber mulch and a "
            "combo climbing-and-swing structure, positioned under the "
            "existing tree canopy for natural shade."
        ),
        "layout_notes": (
            "Lay rubber mulch across the bare soil patch as the play "
            "surface. Position the combo structure under the tree canopy "
            "so climbing and swinging areas both get shade."
        ),
        "shopping_list": ["Impact-Safe Rubber Mulch", "Climbing + Swing Set Combo"],
        "next_steps": [
            "Confirm clearance zones around the structure meet safety guidance",
            "Order mulch sized to the full play area footprint",
            "Install the structure under the tree canopy first, then mulch around it",
        ],
        "placements": [
            {
                "product_id": "surfacing_rubber_mulch",
                "zone": "bare soil patch play footprint",
                "position_hint": "cover full footprint under and around the structure",
            },
            {
                "product_id": "play_structure_combo",
                "zone": "under existing tree canopy",
                "position_hint": "center beneath the canopy for shade",
            },
        ],
    },
    "logistics": {"shipping_location": "30306", "delivery_tier": "standard"},
    "logistics_exchanges": [
        {
            "question_text": "Where should we ship this?",
            "topic": "shipping_location",
            "draft_options": [],
            "tool_call_plan": {"tool_name": "none", "tool_args": {}},
            "ui_component_type": "text_input",
            "chosen_product_id": None,
            "chosen_answer": "30306",
            "task_name": "Shipping & Timing",
        },
        {
            "question_text": "Which delivery speed works for you?",
            "topic": "delivery_speed",
            "draft_options": ["Standard", "Expedited"],
            "tool_call_plan": {
                "tool_name": "shipping_options_lookup",
                "tool_args": {
                    "location": "30306",
                    "product_ids": ["surfacing_rubber_mulch", "play_structure_combo"],
                },
            },
            "ui_component_type": "chip_select",
            "chosen_product_id": "standard",
            "chosen_answer": "Standard",
            "task_name": "Shipping & Timing",
        },
    ],
}

# Standalone task-list edit requests — each references one session's brief
# and initial task_list, exercising TaskListEditor's accept/reject and
# add/remove/rename/reorder paths. Not tied to that session's Q&A/design
# proposal, since editing happens before the per-task Q&A loop even starts.
TASK_EDIT_EXAMPLES = [
    {
        "brief": SESSION_A["brief"],
        "current_task_list": SESSION_A["task_list"],
        "user_edit_request": "Can you also add something about outdoor lighting?",
        "edit_result": "accepted",
        "updated_task_list": SESSION_A["task_list"]
        + [{"task_name": "Lighting", "topic_area": "lighting"}],
        "explanation": "Added a lighting task since that's a supported category.",
    },
    {
        "brief": SESSION_B["brief"],
        "current_task_list": SESSION_B["task_list"],
        "user_edit_request": "Actually drop the color palette task, I don't care about that.",
        "edit_result": "accepted",
        "updated_task_list": [
            {"task_name": "Fencing Materials", "topic_area": "materials"},
            {"task_name": "Budget", "topic_area": "budget"},
        ],
        "explanation": "Removed the color palette task as requested.",
    },
    {
        "brief": SESSION_C["brief"],
        "current_task_list": SESSION_C["task_list"],
        "user_edit_request": "Can we rename 'Furniture' to 'Seating'?",
        "edit_result": "accepted",
        "updated_task_list": [
            {"task_name": "Seating", "topic_area": "furniture"},
            {"task_name": "Shade Structure", "topic_area": "structures"},
            {"task_name": "Budget", "topic_area": "budget"},
        ],
        "explanation": "Renamed the furniture task to Seating.",
    },
    {
        "brief": SESSION_D["brief"],
        "current_task_list": SESSION_D["task_list"],
        "user_edit_request": "Let's talk budget first before anything else.",
        "edit_result": "accepted",
        "updated_task_list": [
            {"task_name": "Budget", "topic_area": "budget"},
            {"task_name": "Garden Bed Materials", "topic_area": "materials"},
            {"task_name": "Irrigation", "topic_area": "irrigation"},
        ],
        "explanation": "Reordered the list to put budget first.",
    },
    {
        "brief": SESSION_E["brief"],
        "current_task_list": SESSION_E["task_list"],
        "user_edit_request": "Can you add a task for installing a swimming pool?",
        "edit_result": "rejected",
        "updated_task_list": SESSION_E["task_list"],
        "explanation": (
            "Swimming pool installation isn't a category this system can "
            "ground with real options yet, so the task list is unchanged."
        ),
    },
    {
        "brief": SESSION_F["brief"],
        "current_task_list": SESSION_F["task_list"],
        "user_edit_request": "Add irrigation for the new plants.",
        "edit_result": "accepted",
        "updated_task_list": SESSION_F["task_list"]
        + [{"task_name": "Irrigation", "topic_area": "irrigation"}],
        "explanation": "Added an irrigation task since that's a supported category.",
    },
    {
        "brief": SESSION_G["brief"],
        "current_task_list": SESSION_G["task_list"],
        "user_edit_request": "Can you add a task for a hot tub?",
        "edit_result": "rejected",
        "updated_task_list": SESSION_G["task_list"],
        "explanation": (
            "A hot tub isn't a category this system can ground with real "
            "options yet, so the task list is unchanged."
        ),
    },
    {
        "brief": SESSION_H["brief"],
        "current_task_list": SESSION_H["task_list"],
        "user_edit_request": "Remove the budget task, we'll figure that out ourselves.",
        "edit_result": "accepted",
        "updated_task_list": [
            {"task_name": "Safety Surfacing", "topic_area": "materials"},
            {"task_name": "Play Structure", "topic_area": "structures"},
        ],
        "explanation": "Removed the budget task as requested.",
    },
]

# Standalone queries — brief-extraction diversity beyond "backyard", no full
# session attached (no frames/QA/design proposal authored for these).
STANDALONE_BRIEF_QUERIES = [
    {
        "raw_query": (
            "We want to turn our patio into an outdoor dining space, "
            "nothing fancy, keep costs low."
        ),
        "brief": {
            "space_type": "patio",
            "stated_goals": ["create an outdoor dining space"],
            "constraints": ["keep costs low"],
            "missing_info": ["seating capacity", "material preference", "style"],
        },
    },
    {
        "raw_query": (
            "Our front yard needs a full makeover, we just moved in and "
            "it's pretty bare."
        ),
        "brief": {
            "space_type": "front yard",
            "stated_goals": ["full makeover of a bare, newly-moved-into space"],
            "constraints": [],
            "missing_info": [
                "budget",
                "style preference",
                "planting vs. hardscape balance",
            ],
        },
    },
]

SESSIONS = [
    SESSION_A,
    SESSION_B,
    SESSION_C,
    SESSION_D,
    SESSION_E,
    SESSION_F,
    SESSION_G,
    SESSION_H,
]
