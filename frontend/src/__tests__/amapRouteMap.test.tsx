import { cleanup, render, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AmapRouteMap } from "../components/AmapRouteMap"
import type { GeoJSONFeatureCollection, RoutePoi } from "../types/route"

const loadAmap = vi.fn()

vi.mock("../utils/loadAmap", () => ({
  loadAmap: () => loadAmap()
}))

describe("AmapRouteMap", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_AMAP_JS_KEY", "test-js-key")
    vi.stubEnv("VITE_AMAP_SECURITY_JS_CODE", "test-security-code")
    loadAmap.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it("binds markers and route polylines to the map when route data is available", async () => {
    const fakeMap = {
      add: vi.fn(),
      destroy: vi.fn(),
      setFitView: vi.fn()
    }
    const markerOptions: unknown[] = []
    const polylineOptions: unknown[] = []
    const overlays = [
      { setMap: vi.fn() },
      { setMap: vi.fn() },
      { setMap: vi.fn() }
    ]

    const AMap = {
      Map: vi.fn(function () {
        return fakeMap
      }),
      Marker: vi.fn(function (options: unknown) {
        markerOptions.push(options)
        return overlays[markerOptions.length - 1]
      }),
      Polyline: vi.fn(function (options: unknown) {
        polylineOptions.push(options)
        return overlays[2]
      })
    }
    vi.stubGlobal("AMap", AMap)
    loadAmap.mockResolvedValue(AMap)

    const pois: RoutePoi[] = [
      { id: "hf_poi_1", name: "合肥 POI 1", longitude: 117.22, latitude: 31.82 },
      { id: "hf_poi_2", name: "合肥 POI 2", longitude: 117.23, latitude: 31.83 }
    ]
    const geojson: GeoJSONFeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            segment_index: 1,
            step_index: 1,
            from_poi_id: "hf_poi_1",
            from_poi_name: "合肥 POI 1",
            to_poi_id: "hf_poi_2",
            to_poi_name: "合肥 POI 2",
            distance_m: 1000,
            duration_s: 600
          },
          geometry: {
            type: "LineString",
            coordinates: [
              [117.22, 31.82],
              [117.23, 31.83]
            ]
          }
        }
      ]
    }

    render(<AmapRouteMap geojson={geojson} pois={pois} />)

    await waitFor(() => {
      expect(AMap.Marker).toHaveBeenCalledTimes(2)
      expect(AMap.Polyline).toHaveBeenCalledTimes(1)
    })

    expect(markerOptions).toEqual([
      expect.objectContaining({ map: fakeMap, position: [117.22, 31.82] }),
      expect.objectContaining({ map: fakeMap, position: [117.23, 31.83] })
    ])
    expect(polylineOptions).toEqual([
      expect.objectContaining({
        map: fakeMap,
        path: [
          [117.22, 31.82],
          [117.23, 31.83]
        ]
      })
    ])
    expect(fakeMap.setFitView).toHaveBeenCalledWith(overlays)
  })
})
