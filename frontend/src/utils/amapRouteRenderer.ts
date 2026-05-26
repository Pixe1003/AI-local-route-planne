import type { RefinedStop } from "../types/plan"

type LngLat = [number, number]

interface RoutePlannerOptions {
  autoFitView: boolean
  hideMarkers: boolean
  map: AMap.Map
}

interface RoutePlanner {
  search: (
    origin: LngLat,
    destination: LngLat,
    callback: (status: string, result: unknown) => void
  ) => void
}

type RoutePlannerConstructor = new (options: RoutePlannerOptions) => RoutePlanner

export type AmapRouteApi = typeof AMap & {
  Driving?: RoutePlannerConstructor
  Walking?: RoutePlannerConstructor
}

interface RenderAmapRouteSegmentsInput {
  AMap: AmapRouteApi
  isDisposed?: () => boolean
  map: AMap.Map
  stops: RefinedStop[]
}

export function renderAmapRouteSegments({
  AMap,
  isDisposed = () => false,
  map,
  stops
}: RenderAmapRouteSegmentsInput) {
  const planners: RoutePlanner[] = []
  if (stops.length < 2) return planners

  for (let index = 0; index < stops.length - 1; index += 1) {
    const origin = stopToLngLat(stops[index])
    const destination = stopToLngLat(stops[index + 1])
    const Planner = routePlannerForMode(AMap, stops[index].transport_to_next?.mode)

    if (!Planner) {
      addFallbackSegment(AMap, map, origin, destination)
      continue
    }

    const planner = new Planner({ map, hideMarkers: true, autoFitView: false })
    planners.push(planner)

    try {
      planner.search(origin, destination, status => {
        if (!isDisposed() && status !== "complete") {
          addFallbackSegment(AMap, map, origin, destination)
        }
      })
    } catch {
      if (!isDisposed()) {
        addFallbackSegment(AMap, map, origin, destination)
      }
    }
  }

  return planners
}

function routePlannerForMode(AMap: AmapRouteApi, mode?: string | null) {
  return mode === "walking" ? AMap.Walking : AMap.Driving
}

function stopToLngLat(stop: RefinedStop): LngLat {
  return [stop.longitude, stop.latitude]
}

function addFallbackSegment(AMap: AmapRouteApi, map: AMap.Map, origin: LngLat, destination: LngLat) {
  const line = new AMap.Polyline({
    path: [origin, destination],
    strokeColor: "#1677ff",
    strokeOpacity: 0.9,
    strokeWeight: 6,
    lineJoin: "round"
  })
  map.add(line)
}
