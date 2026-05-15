import { useEffect, useMemo, useRef, useState } from "react"

import { loadAmap, type AMapMapInstance, type AMapOverlayInstance } from "../utils/loadAmap"
import type { GeoJSONFeatureCollection, RoutePoi } from "../types/route"

interface AmapRouteMapProps {
  pois: RoutePoi[]
  geojson: GeoJSONFeatureCollection | null
}

const HEFEI_CENTER: [number, number] = [117.2272, 31.8206]

export function AmapRouteMap({ pois, geojson }: AmapRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<AMapMapInstance | null>(null)
  const overlaysRef = useRef<AMapOverlayInstance[]>([])
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
      mapRef.current?.destroy()
      mapRef.current = null
    }
  }, [center, jsKey, securityJsCode])

  useEffect(() => {
    if (status !== "ready" || !mapRef.current || !window.AMap) return

    overlaysRef.current.forEach(overlay => overlay.setMap(null))
    const overlays: AMapOverlayInstance[] = []
    const map = mapRef.current
    pois.forEach((poi, index) => {
      overlays.push(
        new window.AMap!.Marker({
          map,
          position: [poi.longitude, poi.latitude],
          title: poi.name,
          content: `<div class="amap-route-marker" title="${escapeHtml(poi.name)}">${index + 1}</div>`,
          zIndex: 120 + index
        })
      )
    })
    routePaths(geojson).forEach(path => {
      overlays.push(
        new window.AMap!.Polyline({
          map,
          path,
          strokeColor: "#0b6bff",
          strokeOpacity: 0.95,
          strokeWeight: 8,
          lineJoin: "round",
          zIndex: 80
        })
      )
    })
    overlaysRef.current = overlays
    if (overlays.length) {
      map.setFitView(overlays)
    }
  }, [geojson, pois, status])

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

function routePaths(geojson: GeoJSONFeatureCollection | null): [number, number][][] {
  if (!geojson?.features.length) return []
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
  return Array.from(bySegment.values()).filter(path => path.length >= 2)
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
}
