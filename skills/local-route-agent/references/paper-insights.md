# Paper Insights for AIroute

Use this reference when design decisions need the research rationale behind the local route-planning Agent. The papers support a controllable Harness Agent rather than a prompt-only chatbot.

## Paper Mapping

| Paper | Main Idea | AIroute Design Implication |
| --- | --- | --- |
| `3-7643-7363-6_5.pdf` / SCATEAgent | Context-aware multi-modal travel agents fuse routes, congestion, incidents, weather, schedules, and user context; software agents adapt to travel events. | Maintain explicit user/profile/context/event state. Use event-driven replanning and multi-source information fusion. Avoid over-deep AI for MVP; combine rules, state machines, and tools. |
| `978-3-030-33506-9_35.pdf` / Optimal route recommendation with GA | Personalized tourism routes can be optimized with genetic algorithms when candidate combinations grow large. | Greedy/beam is acceptable for MVP; GA/local search becomes useful as candidate count and constraints grow. Define a fitness function before choosing the algorithm. |
| `978-3-030-50454-0_30.pdf` / OD destination prediction | Destination prediction can work from departure time/location by supplementing candidate destinations and extracting statistical, temporal, spatial-neighbor, and graph features. | Add cold-start candidate supplementation. Use time, location, nearby clusters, and co-visit/popularity patterns when user input is sparse. |
| `978-3-032-05781-5_12.pdf` / Path finding with user requests | Tourist routes can be formulated as graph/path optimization under user constraints such as time, distance, cost, and requested spots. | Treat itinerary planning as constrained path search. User must-visit and max distance/time should be hard constraints, not decorative preferences. |
| `s10115-017-1056-y.pdf` / PersTour | Personalized tours use POI popularity, user interests, visit durations, recency, start/end POIs, and time limits, modeled as an orienteering problem. | Personalize dwell time and interest weights. Start/end POIs and time budget must be modeled explicitly. |
| `s12652-018-1081-z.pdf` / Healthy personalized route recommendation | Online travel notes can be mined for scenic-spot topics, hierarchy, features, and classic path structures. | UGC should produce tags, risks, route patterns, and area/scene structure, not only short quotes. |
| `s40558-025-00318-2.pdf` / ILSAP itinerary planning | Interest prediction from historical sequences and photo/visual features plus POI popularity, time-slot favor, and transition probability improves itinerary planning; iterated local search escapes local optima. | Score both user interest and POI characteristics. Consider time-slot fit and transition/co-visit probability. Local search can improve route order after initial construction. |
| `s44443-025-00178-0.pdf` / I-AIR | Intention-aware itinerary recommendation fuses ratings, likes, visits, dwell time, and click signals using Transformer-GCN, then builds feasible routes with a lightweight greedy planner. | Keep a multi-signal scoring abstraction even if MVP uses rules. Future models can plug into the same score breakdown and planner contract. |
| `The_Impact_of_AI_on_Digital_Qu.PDF` | AI-enabled travel website pages show meaningful differences in Lighthouse metrics; mobile performance remains a concern. | Keep route UI fast and mobile-first. Load AI explanations asynchronously, cache expensive outputs, and avoid blocking first render on AI. |
| `tourismhosp-06-00036.pdf` | Travel booking chatbots can reduce booking intention versus humans, especially in negative scenarios; human-like design and human fallback improve acceptance. | Explanation tone, user control, alternatives, and graceful failure matter. In negative route outcomes, offer options instead of pretending certainty. |
| `WHERE_SUSTAINABILITY_MEETS_INT.pdf` | AI improves tourist experience partly through smart-destination capabilities and data-sharing infrastructure. | Design interfaces for real POI, UGC, weather, queue, deal, booking, map, and destination service data even when MVP uses local seed data. |

## Consolidated Engineering Rules

1. Build a Harness Agent, not a route-generating prompt.
2. Represent user need, context, candidates, evidence, routes, validation, events, and versions as state.
3. Use multi-source candidate retrieval and keep provenance.
4. Treat UGC as evidence, sentiment, risk, and route-pattern data.
5. Personalize dwell time, not just POI selection.
6. Optimize the route as a constrained graph/orienteering-style problem.
7. Validate before explaining.
8. Replan by event severity: minor, partial, full.
9. Keep all recommendations explainable and data-backed.
10. Design for future smart-destination integrations while preserving local mock fallback.

## Suggested MVP Heuristics

- Retrieval: selected POIs + category match + text/tag match + nearby/popular fallback.
- POI score: interest + quality + context + UGC + service closure - queue/price/distance/risk penalties.
- Route construction: choose a route skeleton by style, insert high-score required categories, then order by geography/time rhythm.
- Route improvement: swap adjacent stops or replace the weakest stop when validation fails.
- Replanning: preserve confirmed/completed stops unless the user explicitly asks for a full reset.
- Explanation: cite one user preference, one POI attribute, one UGC/evidence item, and one route-level tradeoff where possible.

## Hackathon Demo Priorities

- Half-day tourist route: local food, photo spots, coffee, low queue, fixed end time.
- Couple night route: dinner, atmosphere, photo/night view, relaxed pace.
- Family rainy-day route: indoor POIs, low walking, safety/rest, child-friendly tags.
- Show one dynamic adjustment: fewer queues, cheaper, rainy indoor, compressed to two hours, or added cafe.
