# AI 本地路线智能规划系统

美团黑客松题目「AI 本地路线智能规划」的可运行全栈脚手架。主链路已经打通：输入出行需求、生成 POI 推荐池、勾选候选、生成 3 条风格化路线，并支持对话调整。

## 技术栈

- 后端：FastAPI、Pydantic、SQLAlchemy 模型、DeepSeek 适配边界、本地 seed 数据兜底
- 前端：React、TypeScript、Vite、Zustand、axios、lucide-react
- 数据：PostgreSQL 表模型、Chroma 路径预留、内置上海 POI/UGC mock
- 地图：高德接入位预留，当前提供本地距离兜底视图

## 本地启动

```bash
python -m pip install -e backend[dev]
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

前端需要 Node/npm：

```bash
cd frontend
npm install
npm run dev
```

访问：

- 后端健康检查：http://127.0.0.1:8000/health
- API 文档：http://127.0.0.1:8000/docs
- 前端：http://127.0.0.1:5173

## Docker 启动

```bash
cp .env.example .env
docker compose up --build
```

## 核心 API

- `POST /api/pool/generate`
- `POST /api/plan/generate`
- `POST /api/chat/adjust`
- `GET /api/meta/personas`
- `GET /api/meta/cities`
- `GET /api/poi/{poi_id}`

## 验证

```bash
$env:PYTHONPATH='backend'; python -m pytest backend/tests/test_demo_flow.py -q
```
