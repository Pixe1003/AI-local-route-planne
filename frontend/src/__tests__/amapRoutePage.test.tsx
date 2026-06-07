import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AmapRoutePage } from "../pages/AmapRoutePage"
import { useAmapRouteStore } from "../store/amapRouteStore"
import type { RouteChainRequest, RouteChainResponse } from "../types/route"

const createRouteChain = vi.fn()
const adjustRouteRecommendation = vi.fn()
const adjustAgentRoute = vi.fn()

vi.mock("../api/route", () => ({
  createRouteChain: (request: RouteChainRequest) => createRouteChain(request)
}))

vi.mock("../api/chat", () => ({
  adjustRouteRecommendation: (payload: unknown) => adjustRouteRecommendation(payload)
}))

vi.mock("../api/agent", () => ({
  adjustAgentRoute: (payload: unknown) => adjustAgentRoute(payload)
}))

const routeResult: RouteChainResponse = {
  mode: "driving",
  ordered_pois: [
    {
      id: "sh_poi_001",
      name: "外滩",
      longitude: 121.49,
      latitude: 31.24,
      category: "scenic"
    },
    {
      id: "sh_poi_002",
      name: "豫园",
      longitude: 121.48,
      latitude: 31.23,
      category: "culture"
    }
  ],
  total_distance_m: 1500,
  total_duration_s: 600,
  segments: [
    {
      segment_index: 1,
      from_poi_id: "sh_poi_001",
      from_poi_name: "外滩",
      to_poi_id: "sh_poi_002",
      to_poi_name: "豫园",
      distance_m: 1500,
      duration_s: 600
    }
  ],
  geojson: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          segment_index: 1,
          step_index: 1,
          from_poi_id: "sh_poi_001",
          from_poi_name: "外滩",
          to_poi_id: "sh_poi_002",
          to_poi_name: "豫园",
          distance_m: 1500,
          duration_s: 600
        },
        geometry: {
          type: "LineString",
          coordinates: [
            [121.49, 31.24],
            [121.48, 31.23]
          ]
        }
      }
    ]
  }
}

describe("AmapRoutePage", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_AMAP_JS_KEY", "")
    vi.stubEnv("VITE_AMAP_SECURITY_JS_CODE", "")
    createRouteChain.mockReset()
    adjustRouteRecommendation.mockReset()
    adjustAgentRoute.mockReset()
    createRouteChain.mockResolvedValue(routeResult)
    adjustRouteRecommendation.mockResolvedValue({
      intent_type: "avoid_queue",
      updated_plan: null,
      assistant_message: "已按少排队重新推荐 POI",
      requires_confirmation: false,
      recommended_poi_ids: ["sh_poi_003", "sh_poi_004", "sh_poi_005"],
      alternative_poi_ids: ["sh_poi_006"]
    })
    adjustAgentRoute.mockResolvedValue({
      session_id: "adjusted_session",
      trace_id: "trace_adjusted",
      phase: "DONE",
      ordered_poi_ids: ["sh_poi_002", "sh_poi_003", "sh_poi_004"],
      pool: null,
      route_chain: null,
      story_plan: {
        theme: "Adjusted Story",
        narrative: "Adjusted by feedback.",
        fallback_used: true,
        dropped: [],
        stops: []
      },
      validation: { is_valid: true, issues: [], repaired_count: 0 },
      critique: null,
      steps: [{ tool_name: "parse_feedback", args: {}, observation_summary: "Parsed", latency_ms: 1 }]
    })
    useAmapRouteStore.setState({ routeRequest: null })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it("renders a stored agent route chain without refetching the same route", async () => {
    createRouteChain.mockRejectedValue(new Error("Network Error"))
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "quiet route",
      route_chain: routeResult
    })

    const { container } = render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(container.querySelector(".route-service-shell")).toBeInTheDocument()
    expect(container.querySelector(".route-service-summary")).toBeInTheDocument()
    expect(await screen.findByText("1.5 km")).toBeInTheDocument()
    expect(screen.getAllByText("10 分钟").length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText("Network Error")).not.toBeInTheDocument()
    expect(createRouteChain).not.toHaveBeenCalled()
  })

  it("calls route-chain with stored UGC POI ids and renders Amap route results", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "顺路拍照"
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_001", "sh_poi_002"]
      })
    })
    expect((await screen.findAllByText("外滩 → 豫园")).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText("1.5 km").length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText("10 分钟").length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/高德 JS Key 未配置/)).toBeInTheDocument()
  })

  it("still calls route-chain when a stored transport notice exists", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "route with previous notice",
      transport_notice: "previous backend route notice"
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_001", "sh_poi_002"]
      })
    })
    expect(await screen.findByText("1.5 km")).toBeInTheDocument()
  })

  it("keeps a text route available when the route-chain request fails", async () => {
    createRouteChain.mockRejectedValue(new Error("AMAP_CONFIG_MISSING"))
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      pool: {
        pool_id: "pool_1",
        categories: [
          {
            name: "路线点",
            description: "demo",
            pois: [
              {
                id: "sh_poi_001",
                name: "外滩",
                category: "scenic",
                latitude: 31.24,
                longitude: 121.49,
                rating: 4.8,
                price_per_person: null,
                cover_image: null,
                distance_meters: 200,
                why_recommend: "适合顺路拍照",
                highlight_quote: "演示 UGC",
                keywords: [],
                estimated_queue_min: 10,
                suitable_score: 0.9,
                score_breakdown: {},
                retrieval_provenance: [],
                evidence_snippets: []
              },
              {
                id: "sh_poi_002",
                name: "豫园",
                category: "culture",
                latitude: 31.23,
                longitude: 121.48,
                rating: 4.7,
                price_per_person: null,
                cover_image: null,
                distance_meters: 500,
                why_recommend: "适合室内文化体验",
                highlight_quote: "演示 UGC",
                keywords: [],
                estimated_queue_min: 12,
                suitable_score: 0.85,
                score_breakdown: {},
                retrieval_provenance: [],
                evidence_snippets: []
              }
            ]
          }
        ],
        default_selected_ids: ["sh_poi_001", "sh_poi_002"],
        meta: {
          total_count: 2,
          generated_at: "2026-05-02T00:00:00Z",
          user_persona_summary: "demo"
        }
      }
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("地图路线暂不可用，以下为文字路线建议。")).toBeInTheDocument()
    expect(screen.getByText("外滩")).toBeInTheDocument()
    expect(screen.getByText("豫园")).toBeInTheDocument()
  })

  it("updates recommended POIs from user feedback and reruns Amap route generation", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      pool_id: "pool_1",
      free_text: "顺路拍照",
      date: "2026-05-02",
      time_window: { start: "14:00", end: "20:00" }
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_001", "sh_poi_002"]
      })
    })

    fireEvent.change(screen.getByLabelText("调整推荐"), {
      target: { value: "少排队一点，不要商场" }
    })
    fireEvent.submit(screen.getByTestId("route-feedback-form"))

    await waitFor(() => {
      expect(adjustRouteRecommendation).toHaveBeenCalledWith(
        expect.objectContaining({
          pool_id: "pool_1",
          current_poi_ids: ["sh_poi_001", "sh_poi_002"],
          user_message: "少排队一点，不要商场"
        })
      )
    })
    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_003", "sh_poi_004", "sh_poi_005"]
      })
    })
    expect(screen.getByText("已按少排队重新推荐 POI")).toBeInTheDocument()
  })

  it("uses agent adjust when a session id is available", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      session_id: "agent_session_1",
      free_text: "quiet route",
      date: "2026-05-02",
      time_window: { start: "14:00", end: "20:00" }
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    fireEvent.change(await screen.findByLabelText("调整推荐"), {
      target: { value: "第二站换近的火锅，预算到250" }
    })
    fireEvent.submit(screen.getByTestId("route-feedback-form"))

    await waitFor(() => {
      expect(adjustAgentRoute).toHaveBeenCalledWith({
        parent_session_id: "agent_session_1",
        user_message: "第二站换近的火锅，预算到250"
      })
    })
    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_002", "sh_poi_003", "sh_poi_004"]
      })
    })
    expect(adjustRouteRecommendation).not.toHaveBeenCalled()
    expect(await screen.findByText("Adjusted Story")).toBeInTheDocument()
  })

  it("renders agent story theme, narrative, and stop evidence when provided", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "quiet route",
      story_plan: {
        theme: "Story Route",
        narrative: "A compact story-first route.",
        fallback_used: true,
        dropped: [],
        stops: [
          {
            poi_id: "sh_poi_001",
            role: "opener",
            why: "Start here because the UGC says it is scenic.",
            ugc_quote_ref: "pool:sh_poi_001",
            ugc_quote: "scenic and easy to start",
            suggested_dwell_min: 45
          },
          {
            poi_id: "sh_poi_002",
            role: "main",
            why: "Continue here for a quiet culture stop.",
            ugc_quote_ref: "pool:sh_poi_002",
            ugc_quote: "quiet culture stop",
            suggested_dwell_min: 45
          }
        ]
      }
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("Story Route")).toBeInTheDocument()
    expect(screen.getByText("A compact story-first route.")).toBeInTheDocument()
    expect(screen.getByText("Start here because the UGC says it is scenic.")).toBeInTheDocument()
    expect(screen.getByText("scenic and easy to start")).toBeInTheDocument()
  })

  it("renders pool retrieval evidence, provenance, and origin distance for route POIs", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "quiet route",
      pool: {
        pool_id: "pool_1",
        default_selected_ids: ["sh_poi_001", "sh_poi_002"],
        meta: {
          total_count: 2,
          generated_at: "2026-05-10T00:00:00Z",
          user_persona_summary: "demo",
          data_warning: "FAISS index missing"
        },
        categories: [
          {
            name: "顺路打卡",
            description: "demo",
            pois: [
              {
                id: "sh_poi_001",
                name: "外滩",
                category: "scenic",
                latitude: 31.24,
                longitude: 121.49,
                rating: 4.8,
                price_per_person: null,
                cover_image: null,
                distance_meters: 250,
                why_recommend: "semantic hit",
                highlight_quote: "真实 UGC 说这里很出片",
                keywords: ["出片"],
                estimated_queue_min: 10,
                suitable_score: 0.92,
                score_breakdown: {},
                retrieval_score: 0.88,
                retrieval_provenance: ["semantic_ugc_review"],
                evidence_snippets: [
                  {
                    doc_id: "ugc_review:sh_poi_001:0",
                    source_type: "ugc_review",
                    text: "真实 UGC 说这里很出片",
                    score: 0.88
                  }
                ]
              }
            ]
          }
        ]
      }
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("semantic_ugc_review")).toBeInTheDocument()
    expect(screen.getByText("真实 UGC 说这里很出片")).toBeInTheDocument()
    expect(screen.getByText("距出发点 250 m")).toBeInTheDocument()
    expect(screen.getByText("FAISS index missing")).toBeInTheDocument()
  })

  it("shows the agent thinking panel when trace steps are stored", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "quiet route",
      agent_steps: [
        { tool_name: "parse_intent", args: {}, observation_summary: "Parsed intent", latency_ms: 2 },
        { tool_name: "compose_story", args: {}, observation_summary: "Composed story", latency_ms: 3 },
        { tool_name: "critique", args: {}, observation_summary: "Approved", latency_ms: 1 }
      ]
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("Agent 思考")).toBeInTheDocument()
    expect(screen.getByText("在理解需求")).toBeInTheDocument()
    expect(screen.getByText("在编排路线")).toBeInTheDocument()
    expect(screen.getByText("最后审稿")).toBeInTheDocument()
  })

  it("highlights only the selected Pareto variant when labels repeat", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "quiet route",
      route_chain: routeResult,
      route_variants: [
        {
          label: "frontier",
          ordered_ids: ["sh_poi_001", "sh_poi_002"],
          solver: "exact",
          interest: 100,
          time_min: 60,
          cost: 80,
          queue_min: 20,
          metrics: { interest: 100, time: 60, cost: 80, queue: 20 },
          objective_value: 100,
          non_dominated: true
        },
        {
          label: "frontier",
          ordered_ids: ["sh_poi_002", "sh_poi_003"],
          solver: "exact",
          interest: 90,
          time_min: 45,
          cost: 60,
          queue_min: 10,
          metrics: { interest: 90, time: 45, cost: 60, queue: 10 },
          objective_value: 90,
          non_dominated: true
        }
      ]
    })

    const { container } = render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("1.5 km")).toBeInTheDocument()
    expect(container.querySelectorAll(".route-variant-card.active")).toHaveLength(1)
    const variantButtons = container.querySelectorAll(".route-variant-button")

    fireEvent.click(variantButtons[1])

    await waitFor(() => {
      expect(createRouteChain).toHaveBeenCalledWith({
        mode: "driving",
        poi_ids: ["sh_poi_002", "sh_poi_003"]
      })
    })
    expect(useAmapRouteStore.getState().routeRequest).toEqual(
      expect.objectContaining({
        poi_ids: ["sh_poi_002", "sh_poi_003"],
        route_chain: null,
        active_variant_label: "frontier"
      })
    )
    const cards = container.querySelectorAll(".route-variant-card")
    expect(container.querySelectorAll(".route-variant-card.active")).toHaveLength(1)
    expect(cards[1]).toHaveClass("active")
  })

  it("renders Pareto business labels, tradeoff reasons, and low-diversity notice", async () => {
    useAmapRouteStore.getState().setRouteRequest({
      mode: "driving",
      poi_ids: ["sh_poi_001", "sh_poi_002"],
      source: "ugc_instant_route",
      free_text: "rainy indoor route",
      route_chain: routeResult,
      route_variants: [
        {
          label: "interest",
          ordered_ids: ["sh_poi_001", "sh_poi_002"],
          solver: "exact",
          interest: 100,
          time_min: 60,
          cost: 80,
          queue_min: 20,
          metrics: { interest: 100, time: 60, cost: 80, queue: 20 },
          objective_value: 100,
          non_dominated: true,
          diversity_score: 0.2,
          business_label: "室内稳妥",
          tradeoff_reason: "雨天优先室内点位，但候选受限，方案差异较小。"
        },
        {
          label: "balanced",
          ordered_ids: ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
          solver: "exact",
          interest: 92,
          time_min: 58,
          cost: 76,
          queue_min: 18,
          metrics: { interest: 92, time: 58, cost: 76, queue: 18 },
          objective_value: 92,
          non_dominated: true,
          diversity_score: 0.25,
          business_label: "兴趣优先",
          tradeoff_reason: "保留高兴趣点位，轻微牺牲路线差异。"
        }
      ]
    })

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

    expect(await screen.findByText("室内稳妥")).toBeInTheDocument()
    expect(screen.getByText("雨天优先室内点位，但候选受限，方案差异较小。")).toBeInTheDocument()
    expect(screen.getByText("候选受限，方案差异较小")).toBeInTheDocument()
  })
})
