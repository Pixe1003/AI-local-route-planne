# AI 本地路线智能规划系统

美团黑客松「现在就出发 · AI 本地路线智能规划」MVP。当前产品主线是：

`UGC 偏好冷启动 -> RAG 候选召回 -> 一键即时路线 -> 备选 POI 调整 -> 对话重规划`

项目不接真实用户隐私数据，用户历史偏好由首屏 UGC Feed 的收藏行为模拟。地图、距离、LLM 和 embedding 能力都保留扩展接口；默认主路径使用合肥 POI SQLite + Chroma RAG，外部能力不可用时降级到本地 seed 数据和确定性规划链路。

## 当前能力

- UGC Feed 首屏：展示小红书/大众点评式内容卡片，用户收藏 POI 形成偏好。
- 偏好快照：根据收藏 POI 生成标签、类别、关键词权重。
- 真实 RAG：从 `data/processed/hefei_pois.sqlite` 读取 POI 属性、商圈、标签和高频关键词，构建 Chroma 向量索引并返回可追踪证据。
- 即时路线：生成一条主路线，覆盖至少 3 个 POI，并包含餐饮与文化/娱乐/景点类 POI。
- 多目标评分：综合用户提示词、收藏偏好、距离、预算、排队、评分和 UGC 证据。
- 备选 POI：展示可替换地点，可一键替换路线中的某一站。
- 对话重规划：支持少排队、省钱、下雨、少走路、压缩时间、替换备选等调整。
- 兜底机制：LLM 或外部 API 不可用时，仍可用规则模板和本地距离估算生成路线。

## 技术栈

- Backend: FastAPI, Pydantic, local seed POI/UGC data
- Frontend: React, TypeScript, Vite, Zustand, axios, lucide-react
- Tests: pytest, Vitest

## 本地启动

Backend:

```powershell
$env:PYTHONPATH='backend'
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

可选：构建合肥 POI RAG 索引：

```powershell
$env:PYTHONPATH='backend'
python -m app.repositories.rag_index build --city hefei --source data/processed/hefei_pois.sqlite --reset
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
- `POST /api/plan/generate`
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
