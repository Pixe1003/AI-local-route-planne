# 高德 POI 路线规划 Demo

这是一个从零初始化的 Demo 项目，用于后续实现“基于高德 API 的多 POI 路线串联与地图可视化”。

当前阶段只包含基础骨架：

- 后端：FastAPI
- 前端：Next.js App Router + TypeScript
- 后端健康检查接口：`GET /api/health`
- 前端初始化首页

当前阶段尚未实现：

- 高德 Web 服务 API 调用
- 高德 JS API 地图加载
- POI 选择
- 路线规划
- GeoJSON 转换
- 数据库
- TSP 或自动排序

## 目录结构

```text
backend/
  app/
    api/
    schemas/
    services/
    main.py
  tests/
  pyproject.toml
  .env.example
frontend/
  app/
    layout.tsx
    page.tsx
    globals.css
  components/
  lib/
  package.json
  tsconfig.json
  next.config.ts
  .env.example
README.md
.gitignore
```

## 后端安装依赖

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## 后端启动

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

服务默认地址：

```text
http://localhost:8000
```

健康检查：

```text
GET http://localhost:8000/api/health
```

返回：

```json
{"status": "ok"}
```

## 后端测试

```bash
cd backend
.venv\Scripts\activate
pytest
```

## 前端安装依赖

```bash
cd frontend
npm install
```

## 前端启动

```bash
cd frontend
npm run dev
```

前端默认地址：

```text
http://localhost:3000
```

## 环境变量

不要提交真实 `.env` 或 `.env.local`。

后端复制示例：

```bash
cd backend
copy .env.example .env
```

前端复制示例：

```bash
cd frontend
copy .env.example .env.local
```

请只在本地环境文件中填写真实高德 Key。

## 下一阶段建议

1. 定义 mock POI 数据结构。
2. 定义前后端共享的路线请求/响应字段。
3. 后端新增路线规划接口，但先返回 mock GeoJSON。
4. 前端实现 POI 多选和顺序列表。
5. 前端接入高德 JS API 并显示地图与 Marker。
6. 后端接入高德 walking/driving Web API。
7. 将高德返回结果转换为 GeoJSON 并在前端绘制 Polyline。
