import axios from "axios"

export function getApiErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: unknown } }).response
    const data = response?.data
    if (typeof data === "object" && data !== null && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === "object" && detail !== null && "message" in detail) {
        const message = (detail as { message?: unknown }).message
        if (typeof message === "string" && message.trim()) return message
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
