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

SEARCH_UGC_EVIDENCE = {
    "name": "search_ugc_evidence",
    "description": "Search simulated UGC reviews for evidence that supports POI ranking and route narration.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "city": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    },
}

RECALL_SIMILAR_SESSIONS = {
    "name": "recall_similar_sessions",
    "description": "Retrieve semantically similar past route sessions from the user's memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    },
}

COMPOSE_STORY = {
    "name": "compose_story",
    "description": "Compose a themed 3-5 POI route story with grounded UGC evidence.",
    "parameters": {
        "type": "object",
        "properties": {
            "max_stops": {"type": "integer"},
        },
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

PARSE_FEEDBACK = {
    "name": "parse_feedback",
    "description": "Parse route adjustment feedback into slot deltas such as target stop, category hint, and budget.",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
        },
        "required": ["message"],
    },
}

REPLAN_BY_EVENT = {
    "name": "replan_by_event",
    "description": "Apply parsed feedback to the current story route and prepare it for route-chain recalculation.",
    "parameters": {"type": "object", "properties": {}},
}

VALIDATE_ROUTE = {
    "name": "validate_route",
    "description": "Validate the composed route against time, budget, queue, and POI constraints.",
    "parameters": {"type": "object", "properties": {}},
}

CRITIQUE = {
    "name": "critique",
    "description": "Review the story route for coherence, evidence grounding, pacing, and feasibility.",
    "parameters": {"type": "object", "properties": {}},
}

FINISH = {
    "name": "finish",
    "description": "Finish the agent run and return the final route result.",
    "parameters": {"type": "object", "properties": {}},
}


TOOL_SCHEMAS = [
    PARSE_INTENT,
    SEARCH_UGC_EVIDENCE,
    RECALL_SIMILAR_SESSIONS,
    RECOMMEND_POOL,
    COMPOSE_STORY,
    GET_AMAP_CHAIN,
    PARSE_FEEDBACK,
    REPLAN_BY_EVENT,
    VALIDATE_ROUTE,
    CRITIQUE,
    FINISH,
]
