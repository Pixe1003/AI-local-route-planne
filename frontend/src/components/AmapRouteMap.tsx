import { useEffect, useMemo, useRef, useState } from "react"

import {
  loadAmap,
  type AMapMapInstance,
  type AMapNamespace,
  type AMapOverlayInstance,
  type AMapRoutePlannerInstance
} from "../utils/loadAmap"
import type { GeoJSONFeatureCollection, RouteMode, RoutePoi } from "../types/route"

interface AmapRouteMapProps {
  pois: RoutePoi[]
  geojson: GeoJSONFeatureCollection | null
  mode?: RouteMode
}

const HEFEI_CENTER: [number, number] = [117.2272, 31.8206]

export function AmapRouteMap({ pois, geojson, mode = "driving" }: AmapRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<AMapMapInstance | null>(null)
  const overlaysRef = useRef<AMapOverlayInstance[]>([])
  const plannersRef = useRef<AMapRoutePlannerInstance[]>([])
  const amapRef = useRef<AMapNamespace | null>(null)
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle")
  const [error, setError] = useState<string | null>(null)
  const jsKey = import.meta.env.VITE_AMAP_JS_KEY
  const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE
  const center = useMemo<[number, number]>(() => {
    const firstPoi = pois[0]
    return firstPoi ? [firstPoi.longitude, firstPoi.latitude] : HEFEI_CENTER
  }, [pois])

  useEffect(() => {
    if (!jsKey || !securityJsCode || !containerRef.current) {
      return
    }

    let cancelled = false
    setStatus("loading")
    setError(null)
    loadAmap(jsKey, securityJsCode)
      .then(AMap => {
        if (cancelled || !containerRef.current) return
        mapRef.current?.destroy()
        const map = new AMap.Map(containerRef.current, {
          center,
          zoom: 12,
          viewMode: "2D"
        })
        amapRef.current = AMap
        mapRef.current = map
        const markReady = () => {
          if (!cancelled) setStatus("ready")
        }
        if (typeof map.on === "function") {
          map.on("complete", markReady)
        } else {
          markReady()
        }
      })
      .catch(loadError => {
        if (cancelled) return
        setStatus("error")
        setError(loadError instanceof Error ? loadError.message : "高德地图加载失败")
      })

    return () => {
      cancelled = true
      overlaysRef.current.forEach(overlay => overlay.setMap(null))
      overlaysRef.current = []
      plannersRef.current.forEach(planner => planner.clear?.())
      plannersRef.current = []
      amapRef.current = null
      mapRef.current?.destroy()
      mapRef.current = null
    }
  }, [center, jsKey, securityJsCode])

  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !amapRef.current) return

    overlaysRef.current.forEach(overlay => overlay.setMap(null))
    plannersRef.current.forEach(planner => planner.clear?.())
    const overlays: AMapOverlayInstance[] = []
    const planners: AMapRoutePlannerInstance[] = []
    const map = mapRef.current
    const AMap = amapRef.current
    pois.forEach((poi, index) => {
      overlays.push(
        new AMap.Marker({
          map,
          position: [poi.longitude, poi.latitude],
          title: poi.name,
          content: `<div class="amap-route-marker" title="${escapeHtml(poi.name)}">${index + 1}</div>`,
          zIndex: 120 + index
        })
      )
    })
    if (pois.length >= 2 && renderJsapiRouteSegments({ AMap, map, mode, pois, overlays, planners })) {
      plannersRef.current = planners
    } else {
      routePaths(geojson, pois).forEach(path => {
        overlays.push(routePolyline(AMap, map, path))
      })
      plannersRef.current = []
    }
    overlaysRef.current = overlays
    if (overlays.length) {
      map.setFitView(overlays)
    }
  }, [geojson, mode, pois, status])

  if (!jsKey || !securityJsCode) {
    return (
      <div className="route-map-fallback">
        <strong>高德 JS Key 未配置</strong>
        <span>后端仍会生成真实路线；配置前端 Key 后这里会显示高德地图。</span>
      </div>
    )
  }

  return (
    <div className="route-map-shell">
      <div aria-label="高德路线地图" className="route-amap-container" ref={containerRef} />
      {status !== "ready" ? (
        <div className="route-map-status" role="status">
          <strong>{status === "loading" ? "高德地图加载中" : "地图暂不可用"}</strong>
          <span>{error ?? "正在准备路线图层"}</span>
        </div>
      ) : null}
    </div>
  )
}

function renderJsapiRouteSegments({
  AMap,
  map,
  mode,
  pois,
  overlays,
  planners
}: {
  AMap: AMapNamespace
  map: AMapMapInstance
  mode: RouteMode
  pois: RoutePoi[]
  overlays: AMapOverlayInstance[]
  planners: AMapRoutePlannerInstance[]
}) {
  const Planner = mode === "walking" ? AMap.Walking : AMap.Driving
  if (!Planner) return false

  pairwise(pois).forEach(([fromPoi, toPoi]) => {
    const origin: [number, number] = [fromPoi.longitude, fromPoi.latitude]
    const destination: [number, number] = [toPoi.longitude, toPoi.latitude]
    const planner = new Planner({ map, hideMarkers: true, autoFitView: false })
    planners.push(planner)
    planner.search(origin, destination, status => {
      if (status !== "complete") {
        overlays.push(routePolyline(AMap, map, [origin, destination]))
      }
    })
  })
  return true
}

function routePaths(geojson: GeoJSONFeatureCollection | null, pois: RoutePoi[]): [number, number][][] {
  if (!geojson?.features.length) return straightRoutePaths(pois)
  const bySegment = new Map<number, [number, number][]>()
  geojson.features.forEach(feature => {
    const coordinates = feature.geometry.coordinates
    if (coordinates.length < 2) return
    const segmentIndex = feature.properties.segment_index
    const path = bySegment.get(segmentIndex) ?? []
    coordinates.forEach(coordinate => {
      const previous = path[path.length - 1]
      if (!previous || previous[0] !== coordinate[0] || previous[1] !== coordinate[1]) {
        path.push(coordinate)
      }
    })
    bySegment.set(segmentIndex, path)
  })
  const paths = Array.from(bySegment.values()).filter(path => path.length >= 2)
  return paths.length ? paths : straightRoutePaths(pois)
}

function straightRoutePaths(pois: RoutePoi[]): [number, number][][] {
  return pairwise(pois).map(([fromPoi, toPoi]) => [
    [fromPoi.longitude, fromPoi.latitude],
    [toPoi.longitude, toPoi.latitude]
  ])
}

function routePolyline(AMap: AMapNamespace, map: AMapMapInstance, path: [number, number][]) {
  return new AMap.Polyline({
    map,
    path,
    strokeColor: "#0b6bff",
    strokeOpacity: 0.95,
    strokeWeight: 8,
    lineJoin: "round",
    zIndex: 80
  })
}

function pairwise(pois: RoutePoi[]): Array<[RoutePoi, RoutePoi]> {
  return pois.slice(0, -1).map((poi, index) => [poi, pois[index + 1]])
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
}
