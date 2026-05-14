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
  adjustAgentRoute: (payload: unknown) => adjustAgentRoute(payload),
  agentTraceStreamUrl: (sessionId: string) => `/api/agent/stream/${sessionId}`
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

    render(
      <MemoryRouter>
        <AmapRoutePage />
      </MemoryRouter>
    )

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
})
