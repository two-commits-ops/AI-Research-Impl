"""Canned per-frame vision output, standing in for a real CV/vision model.

Frames are deliberately authored to be incomplete in different ways, so
FrameCompletenessChecker has real signal to learn "not done yet" from, not
just a single always-complete case.
"""

FRAMES = {
    # --- Session A: worn deck, wants a refresh ---------------------------
    "frame_a1": {
        "frame_id": "frame_a1",
        "visible_elements": ["deck boards", "sliding door", "part of lawn"],
        "cutoff_edges": ["left"],
        "lighting": "bright, midday",
        "notes": "Left edge cuts off before the fence line is visible.",
    },
    "frame_a2": {
        "frame_id": "frame_a2",
        "visible_elements": ["deck boards", "wood fence", "lawn"],
        "cutoff_edges": ["bottom"],
        "lighting": "bright, midday",
        "notes": "Bottom of frame cuts off before showing where the deck meets the grass.",
    },
    "frame_a3": {
        "frame_id": "frame_a3",
        "visible_elements": [
            "deck boards",
            "wood fence",
            "lawn",
            "deck-to-grass transition",
            "sliding door",
        ],
        "cutoff_edges": [],
        "lighting": "bright, midday",
        "notes": "Full deck footprint and boundary visible.",
    },
    # --- Session B: low fence, wants privacy ------------------------------
    "frame_b1": {
        "frame_id": "frame_b1",
        "visible_elements": ["patio", "garden bed", "part of fence"],
        "cutoff_edges": ["right"],
        "lighting": "overcast",
        "notes": "Right side cuts off before the full fence line and neighboring sightline are visible.",
    },
    "frame_b2": {
        "frame_id": "frame_b2",
        "visible_elements": [
            "patio",
            "garden bed",
            "full fence line",
            "neighboring sightline",
        ],
        "cutoff_edges": [],
        "lighting": "overcast",
        "notes": "Full fence line and sightline visible end to end.",
    },
    # --- Session C: dated pool area ---------------------------------------
    "frame_c1": {
        "frame_id": "frame_c1",
        "visible_elements": ["pool", "pool deck", "old lounge chairs"],
        "cutoff_edges": ["right"],
        "lighting": "bright, midday",
        "notes": "Right side cuts off before the far end of the pool.",
    },
    "frame_c2": {
        "frame_id": "frame_c2",
        "visible_elements": [
            "pool",
            "pool deck",
            "old lounge chairs",
            "far end of pool",
        ],
        "cutoff_edges": [],
        "lighting": "bright, midday",
        "notes": "Full pool and deck footprint visible end to end.",
    },
    # --- Session D: vegetable garden expansion ----------------------------
    "frame_d1": {
        "frame_id": "frame_d1",
        "visible_elements": ["existing raised bed", "hose reel"],
        "cutoff_edges": ["left"],
        "lighting": "overcast",
        "notes": "Left half of the existing bed is cut off.",
    },
    "frame_d2": {
        "frame_id": "frame_d2",
        "visible_elements": [
            "existing raised bed",
            "hose reel",
            "fence border",
            "full bed footprint",
        ],
        "cutoff_edges": [],
        "lighting": "overcast",
        "notes": "Full garden bed and fence border visible.",
    },
    # --- Session E: side yard dog run --------------------------------------
    "frame_e1": {
        "frame_id": "frame_e1",
        "visible_elements": ["narrow side yard", "patchy grass"],
        "cutoff_edges": ["far corner"],
        "lighting": "bright, afternoon",
        "notes": "Far fence corner is cut off from view.",
    },
    "frame_e2": {
        "frame_id": "frame_e2",
        "visible_elements": [
            "narrow side yard",
            "patchy grass",
            "wood fence",
            "far fence corner",
        ],
        "cutoff_edges": [],
        "lighting": "bright, afternoon",
        "notes": "Full side yard run, corner to corner, visible.",
    },
    # --- Session F: front yard curb appeal ----------------------------------
    "frame_f1": {
        "frame_id": "frame_f1",
        "visible_elements": ["lawn strip", "front walkway"],
        "cutoff_edges": ["driveway edge"],
        "lighting": "bright, midday",
        "notes": "Driveway-side edge of the yard is cut off.",
    },
    "frame_f2": {
        "frame_id": "frame_f2",
        "visible_elements": [
            "lawn strip",
            "front walkway",
            "bare planting beds",
            "driveway edge",
        ],
        "cutoff_edges": [],
        "lighting": "bright, midday",
        "notes": "Full front yard width visible, driveway to property line.",
    },
    # --- Session G: covered patio + future outdoor kitchen -----------------
    "frame_g1": {
        "frame_id": "frame_g1",
        "visible_elements": ["concrete patio slab", "back wall of house"],
        "cutoff_edges": ["top"],
        "lighting": "bright, midday",
        "notes": "Top of frame cuts off the roofline where a cover would attach.",
    },
    "frame_g2": {
        "frame_id": "frame_g2",
        "visible_elements": [
            "concrete patio slab",
            "back wall of house",
            "roofline",
            "open sky above patio",
        ],
        "cutoff_edges": [],
        "lighting": "bright, midday",
        "notes": "Full patio slab and roofline visible.",
    },
    # --- Session H: kids play area ------------------------------------------
    "frame_h1": {
        "frame_id": "frame_h1",
        "visible_elements": ["open lawn area", "existing tree"],
        "cutoff_edges": ["top"],
        "lighting": "bright, afternoon",
        "notes": "Top of frame cuts off the tree canopy that would provide shade.",
    },
    "frame_h2": {
        "frame_id": "frame_h2",
        "visible_elements": [
            "open lawn area",
            "existing tree",
            "tree canopy",
            "bare soil patch",
        ],
        "cutoff_edges": [],
        "lighting": "bright, afternoon",
        "notes": "Full play area footprint and tree canopy visible.",
    },
}
