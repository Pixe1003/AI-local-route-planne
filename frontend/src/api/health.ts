export interface SystemHealth {
  status: string
  rag?: {
    enabled: boolean
    engine: string
    status?: string
  }
  faiss?: {
    enabled: boolean
    index_exists: boolean
    document_count: number
    status?: string
  }
  amap?: {
    configured: boolean
    status?: string
  }
  memory?: {
    enabled: boolean
    store_exists: boolean
    status?: string
  }
  cache?: {
    status?: string
  }
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const apiBase = import.meta.env.VITE_API_BASE_URL || "/api"
  const rootBase = apiBase.replace(/\/api\/?$/, "") || ""
  const response = await fetch(`${rootBase}/health`)
  if (!response.ok) throw new Error("系统状态检查失败")
  return response.json() as Promise<SystemHealth>
}
