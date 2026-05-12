import axios from "axios"

export function getApiErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: unknown } }).response
    const data = response?.data
    if (typeof data === "object" && data !== null && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === "object" && detail !== null && "message" in detail) {
        const message = (detail as { message?: unknown }).message
        if (typeof message === "string" && message.trim()) {
          const parts = [message]
          const info = (detail as { info?: unknown }).info
          const infocode = (detail as { infocode?: unknown }).infocode
          const segmentIndex = (detail as { segment_index?: unknown }).segment_index
          const fromPoiName = (detail as { from_poi_name?: unknown }).from_poi_name
          const toPoiName = (detail as { to_poi_name?: unknown }).to_poi_name
          if (typeof info === "string" && info.trim()) parts.push(`info: ${info}`)
          if (typeof infocode === "string" && infocode.trim()) parts.push(`infocode: ${infocode}`)
          if (typeof segmentIndex === "number" && typeof fromPoiName === "string" && typeof toPoiName === "string") {
            parts.push(`segment ${segmentIndex}: ${fromPoiName} -> ${toPoiName}`)
          }
          return parts.join(" / ")
        }
      }
      if (typeof detail === "string" && detail.trim()) return detail
    }
  }
  if (error instanceof Error && error.message) return error.message
  return "请求失败"
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 30_000
})

apiClient.interceptors.response.use(
  response => response.data,
  error => Promise.reject(new Error(getApiErrorMessage(error)))
)
