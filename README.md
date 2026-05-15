# AIroute 本地路线推荐系统

美团黑客松 Demo。当前产品主线是：

`UGC 偏好冷启动 -> POI 推荐池 -> 系统排序 -> 高德真实路线 -> 反馈更新推荐 POI`

大模型只负责理解用户需求、辅助 POI 召回/解释和反馈更新；真实路线、距离、耗时、地图线统一由高德路线接口实现。

## 当前能力

- UGC Feed：首页展示本地内容卡片，用户收藏/点赞形成偏好快照。
- POI 推荐：结合提示词、UGC 偏好、预算、排队、类别覆盖、质量和距离惩罚输出有序 POI。
- 高德路线：`POST /api/route/chain` 根据有序 POI 计算真实分段、总距离、总耗时和 GeoJSON。
- 反馈调整：`POST /api/chat/adjust` 在无 `plan_id` 时更新推荐 POI，例如少排队、便宜一点、不要商场。
- 可解释错误：缺少高德 Key、上游失败、未知 POI 会返回前端可展示的错误信息。

旧的 `/api/plan/generate` 和 `/api/trips/*` 仅作为后端兼容接口保留，前端主链路不再使用。

## 技术栈

- Backend: FastAPI, Pydantic, local seed POI/UGC data
- Frontend: React, TypeScript, Vite, Zustand, axios, lucide-react
- Tests: pytest, Vitest

## 配置

后端高德 Web Service Key：

```powershell
AMAP_WEB_SERVICE_KEY=your_amap_web_service_key
AMAP_ROUTE_BASE_URL=https://restapi.amap.com
AMAP_ROUTE_TIMEOUT_SECONDS=15
```

前端高德 JS API：

```powershell
VITE_AMAP_JS_KEY=your_amap_js_key
VITE_AMAP_SECURITY_JS_CODE=your_amap_security_js_code
```

LLM 默认配置为 LongCat OpenAI-compatible API：

```powershell
LLM_PROVIDER=longcat
LLM_BASE_URL=https://api.longcat.chat/openai/v1
LLM_MODEL=LongCat-Flash-Chat
LLM_API_KEY=your_longcat_api_key
```

## 本地启动

Backend:

```powershell
$env:PYTHONPATH='backend'
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

访问地址：

- Backend health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs
- Frontend: http://127.0.0.1:5173

## 核心 API

- `GET /api/ugc/feed`
- `POST /api/preferences/snapshot`
- `POST /api/pool/generate`
- `POST /api/route/chain`
- `POST /api/chat/adjust`
- `GET /api/meta/personas`
- `GET /api/meta/cities`
- `GET /api/poi/{poi_id}`

## 验证

```powershell
$env:PYTHONPATH='backend'
python -m pytest backend/tests -q

cd frontend
npm test
npm run build
```
