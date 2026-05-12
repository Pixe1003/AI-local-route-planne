PARSE_INTENT = {
    "name": "parse_intent",
    "description": "Extract hard constraints and soft route preferences from the user request.",
    "parameters": {
        "type": "object",
        "properties": {
            "free_text": {"type": "string"},
            "selected_poi_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["free_text"],
    },
}

RECOMMEND_POOL = {
    "name": "recommend_pool",
    "description": "Generate a ranked candidate POI pool from profile, preferences, and free text.",
    "parameters": {
        "type": "object",
        "properties": {
            "free_text": {"type": "string"},
            "city": {"type": "string"},
        },
        "required": ["free_text"],
    },
}

GET_AMAP_CHAIN = {
    "name": "get_amap_chain",
    "description": "Build a chained Amap route for ordered POI ids.",
    "parameters": {
        "type": "object",
        "properties": {
            "poi_ids": {"type": "array", "items": {"type": "string"}},
            "mode": {"type": "string", "enum": ["driving", "walking"]},
        },
        "required": ["poi_ids"],
    },
}

FINISH = {
    "name": "finish",
    "description": "Finish the agent run and return the final route result.",
    "parameters": {"type": "object", "properties": {}},
}


TOOL_SCHEMAS = [PARSE_INTENT, RECOMMEND_POOL, GET_AMAP_CHAIN, FINISH]

