import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it } from "vitest"

import { PlanResultPage } from "../pages/PlanResultPage"
import { usePlanStore } from "../store/planStore"
import type { RefinedPlan } from "../types/plan"

const plan: RefinedPlan = {
  plan_id: "plan_demo",
  style: "efficient",
  title: "高效打卡线",
  description: "马上可以走的一条主路线",
  stops: [
    {
      poi_id: "sh_poi_001",
      poi_name: "淮海路本帮菜馆",
      arrival_time: "14:00",
      departure_time: "15:00",
      duration_min: 60,
      why_this_one: "匹配本地菜偏好",
      ugc_evidence: [{ quote: "下午人少", source: "dianping" }],
      latitude: 31.22,
      longitude: 121.45,
      category: "restaurant",
      score_breakdown: { history_preference: 12, total: 88 },
      estimated_queue_min: 15,
      estimated_cost: 64
    },
    {
      poi_id: "sh_poi_019",
      poi_name: "上海中心观光厅",
      arrival_time: "15:20",
      departure_time: "16:10",
      duration_min: 50,
      why_this_one: "顺路拍照",
      ugc_evidence: [{ quote: "视野好", source: "xiaohongshu" }],
      latitude: 31.23,
      longitude: 121.5,
      category: "scenic",
      score_breakdown: { total: 82 },
      estimated_queue_min: 20,
      estimated_cost: 66
    },
    {
      poi_id: "sh_poi_009",
      poi_name: "永康路手冲咖啡",
      arrival_time: "16:30",
      departure_time: "17:10",
      duration_min: 40,
      why_this_one: "低排队休息",
      ugc_evidence: [{ quote: "很安静", source: "dianping" }],
      latitude: 31.21,
      longitude: 121.44,
      category: "cafe",
      score_breakdown: { total: 80 },
      estimated_queue_min: 16,
      estimated_cost: 36
    }
  ],
  summary: {
    total_duration_min: 190,
    total_cost: 166,
    poi_count: 3,
    style_highlights: ["即时可走"],
    tradeoffs: ["停留略紧"],
    dropped_pois: [],
    total_queue_min: 51,
    walking_distance_meters: 1200,
    validation: { is_valid: true, issues: [], repaired_count: 0 }
  },
  alternative_pois: [
    {
      poi_id: "sh_poi_010",
      poi_name: "衡山路露台咖啡",
      category: "cafe",
      replace_stop_index: 2,
      why_candidate: "排队更低，可替换休息点。",
      delta_minutes: 5,
      estimated_queue_min: 12,
      estimated_cost: 65,
      score_breakdown: { total: 76 }
    }
  ]
}

describe("PlanResultPage alternatives", () => {
  beforeEach(() => {
    usePlanStore.setState({
      plans: [plan],
      activePlanId: "plan_demo",
      loading: false,
      error: null,
      chatHistory: []
    })
  })

  it("shows alternative POIs beside the main route", () => {
    render(
      <MemoryRouter>
        <PlanResultPage />
      </MemoryRouter>
    )

    expect(screen.getByRole("heading", { name: "高效打卡线" })).toBeInTheDocument()
    expect(screen.getByText("可替换 POI")).toBeInTheDocument()
    expect(screen.getByText("衡山路露台咖啡")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /替换第 3 站/ })).toBeInTheDocument()
  })
})
