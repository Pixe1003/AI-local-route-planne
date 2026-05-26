/// <reference types="vite/client" />
/// <reference types="@amap/amap-jsapi-types" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_AMAP_JS_KEY: string
  readonly VITE_AMAP_SECURITY_JS_CODE: string
}
