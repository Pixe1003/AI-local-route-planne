import AMapLoader from "@amap/amap-jsapi-loader"

type AMapApi = typeof AMap

let amapPromise: Promise<AMapApi> | null = null

export function hasAmapConfig() {
  return Boolean(import.meta.env.VITE_AMAP_JS_KEY && import.meta.env.VITE_AMAP_SECURITY_JS_CODE)
}

export function loadAmap(): Promise<AMapApi> {
  if (amapPromise) return amapPromise
  ;(window as typeof window & { _AMapSecurityConfig?: { securityJsCode: string } })._AMapSecurityConfig = {
    securityJsCode: import.meta.env.VITE_AMAP_SECURITY_JS_CODE
  }
  amapPromise = AMapLoader.load({
    key: import.meta.env.VITE_AMAP_JS_KEY,
    version: "2.0",
    plugins: ["AMap.Scale", "AMap.ToolBar", "AMap.Driving", "AMap.Walking"]
  }) as Promise<AMapApi>
  return amapPromise
}
