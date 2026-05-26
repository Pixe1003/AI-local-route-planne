import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PlanMap } from "../components/PlanMap"
import type { RefinedPlan } from "../types/plan"

const amapMock = vi.hoisted(() => ({
  configured: true,
  loadAmap: vi.fn(),
  maps: [] as FakeMap[],
  markers: [] as FakeMarker[],
  polylines: [] as FakePolyline[],
  walkingRoutes: [] as FakeRoutePlanner[],
  drivingRoutes: [] as FakeRoutePlanner[],
  routeStatus: "complete"
}))

vi.mock("../utils/amapLoader", () => ({
  hasAmapConfig: () => amapMock.configured,
  loadAmap: amapMock.loadAmap
}))

class FakeMap {
  add = vi.fn()
  setFitView = vi.fn()
  destroy = vi.fn()

  constructor(public container: HTMLElement, public options: Record<string, unknown>) {
    amapMock.maps.push(this)
  }
}

class FakeMarker {
  handlers: Record<string, () => void> = {}

  constructor(public options: Record<string, unknown>) {
    amapMock.markers.push(this)
  }

  on(event: string, handler: () => void) {
    this.handlers[event] = handler
  }
}

class FakePolyline {
  constructor(public options: Record<string, unknown>) {
    amapMock.polylines.push(this)
  }
}

class FakeRoutePlanner {
  searchCalls: Array<{
    origin: [number, number]
    destination: [number, number]
  }> = []

  constructor(public options: Record<string, unknown>) {}

  search(
    origin: [number, number],
    destination: [number, number],
    callback: (status: string, result: unknown) => void
  ) {
    this.searchCalls.push({ origin, destination })
    callback(amapMock.routeStatus, {})
  }
}

class FakeWalking extends FakeRoutePlanner {
  constructor(options: Record<string, unknown>) {
    super(options)
    amapMock.walkingRoutes.push(this)
  }
}

class FakeDriving extends FakeRoutePlanner {
  constructor(options: Record<string, unknown>) {
    super(options)
    amapMock.drivingRoutes.push(this)
  }
}

const plan: RefinedPlan = {
  plan_id: "plan_1",
  style: "efficient",
  title: "合肥路线",
  description: "测试路线",
  stops: [
    {
      poi_id: "poi_a",
      poi_name: "杏花公园",
      arrival_time: "14:00",
      departure_time: "15:00",
      why_this_one: "适合拍照",
      ugc_evidence: [],
      latitude: 31.8781,
      longitude: 117.2764,
      category: "scenic",
      score_breakdown: {},
      transport_to_next: {
        mode: "walking",
        duration_min: 12,
        distance_meters: 900
      }
    },
    {
      poi_id: "poi_b",
      poi_name: "庐州徽菜馆",
      arrival_time: "15:30",
      departure_time: "16:30",
      why_this_one: "本地菜",
      ugc_evidence: [],
      latitude: 31.82,
      longitude: 117.29,
      category: "restaurant",
      score_breakdown: {},
      transport_to_next: {
        mode: "transit",
        duration_min: 24,
        distance_meters: 4200
      }
    },
    {
      poi_id: "poi_c",
      poi_name: "合肥植物园",
      arrival_time: "17:00",
      departure_time: "18:00",
      why_this_one: "适合散步",
      ugc_evidence: [],
      latitude: 31.875,
      longitude: 117.22,
      category: "outdoor",
      score_breakdown: {}
    }
  ],
  summary: {
    total_duration_min: 150,
    total_cost: 88,
    poi_count: 3,
    style_highlights: [],
    tradeoffs: [],
    dropped_pois: [],
    total_queue_min: 0,
    walking_distance_meters: 0,
    validation: { is_valid: true, issues: [], repaired_count: 0 }
  },
  alternative_pois: []
}

describe("PlanMap", () => {
  beforeEach(() => {
    amapMock.configured = true
    amapMock.maps.length = 0
    amapMock.markers.length = 0
    amapMock.polylines.length = 0
    amapMock.walkingRoutes.length = 0
    amapMock.drivingRoutes.length = 0
    amapMock.routeStatus = "complete"
    amapMock.loadAmap.mockReset()
    amapMock.loadAmap.mockResolvedValue({
      Map: FakeMap,
      Marker: FakeMarker,
      Polyline: FakePolyline,
      Walking: FakeWalking,
      Driving: FakeDriving
    })
  })

  it("loads AMap and renders numbered markers plus JSAPI route planners", async () => {
    const onStopClick = vi.fn()

    render(<PlanMap highlightedStopIndex={1} onStopClick={onStopClick} plan={plan} />)

    await waitFor(() => expect(amapMock.maps).toHaveLength(1))
    expect(screen.getByText("高德路网规划 · 本地 POI")).toBeInTheDocument()
    expect(amapMock.markers).toHaveLength(3)
    expect(amapMock.walkingRoutes).toHaveLength(1)
    expect(amapMock.drivingRoutes).toHaveLength(1)
    expect(amapMock.walkingRoutes[0].options).toMatchObject({
      map: amapMock.maps[0],
      hideMarkers: true,
      autoFitView: false
    })
    expect(amapMock.walkingRoutes[0].searchCalls[0]).toEqual({
      origin: [117.2764, 31.8781],
      destination: [117.29, 31.82]
    })
    expect(amapMock.drivingRoutes[0].searchCalls[0]).toEqual({
      origin: [117.29, 31.82],
      destination: [117.22, 31.875]
    })
    expect(amapMock.polylines).toHaveLength(0)

    amapMock.markers[1].handlers.click()

    expect(onStopClick).toHaveBeenCalledWith(1)
    expect(amapMock.maps[0].setFitView).toHaveBeenCalled()
  })

  it("does not rerun route planning when only the highlighted stop changes", async () => {
    const { rerender } = render(<PlanMap highlightedStopIndex={0} plan={plan} />)

    await waitFor(() => expect(amapMock.walkingRoutes).toHaveLength(1))
    expect(amapMock.drivingRoutes).toHaveLength(1)

    rerender(<PlanMap highlightedStopIndex={2} plan={plan} />)

    expect(amapMock.walkingRoutes).toHaveLength(1)
    expect(amapMock.drivingRoutes).toHaveLength(1)
  })

  it("falls back to a straight segment when a JSAPI route search fails", async () => {
    amapMock.routeStatus = "error"

    render(<PlanMap plan={plan} />)

    await waitFor(() => expect(amapMock.polylines).toHaveLength(2))
    expect(amapMock.polylines[0].options).toMatchObject({
      path: [
        [117.2764, 31.8781],
        [117.29, 31.82]
      ],
      strokeColor: "#1677ff"
    })
  })

  it("uses the local fallback view when AMap keys are missing", () => {
    amapMock.configured = false

    render(<PlanMap plan={plan} />)

    expect(screen.getByText("高德地图未配置 · 本地距离兜底视图")).toBeInTheDocument()
    expect(amapMock.loadAmap).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "1" })).toBeInTheDocument()
  })
})
