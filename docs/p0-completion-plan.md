# P0 完善方案 · 从 Demo 到可上线成品

> 范围：当前代码（`codex/real-rag-upgrade` 分支）距离一个能在评委面前经得起追问、且能多次稳定演示的成品，最关键的 4 个 P0 缺口。每项含：问题与证据、影响、可参照的解决方案（含代码骨架与改动文件）、验收标准、工作量估计。
>
> P1 小修（route_repairer 补 city、删 sqlalchemy 死依赖、README 补充）已完成，不在本文。

## 优先级总览

| 编号 | 问题 | 影响面 | 工作量 | 风险 |
| --- | --- | --- | --- | --- |
| P0-1 | 地图是假的（SVG mock，未接真实高德 JS） | 演示观感 / 核心卖点 | 0.5–1 天 | 低（key 已就绪） |
| P0-2 | LLM / Embedding / 高德 默认全程兜底，未验证真实链路 | "AI 智能"可信度 | 0.5 天（配置）+ 0.5 天（可观测） | 中（依赖外部 key/网络） |
| P0-3 | 所有状态内存字典，重启即丢、不可横向扩展 | 数据可靠性 | 1 天 | 中（涉及读写路径） |
| P0-4 | POI 数据体量存疑，且 sqlite 未入库、不可复现 | 链路稳定性 / 团队协作 | 0.5–1 天 | 中 |

建议落地顺序：**P0-4 → P0-2 → P0-1 → P0-3**（先确保数据与真实链路可用，再做观感，最后做持久化）。

---

## P0-1 · 接入真实高德地图

### 问题与证据

- `frontend/src/components/PlanMap.tsx` 当前是 SVG 折线 + CSS 方块标记的兜底视图，工具栏文字写着"高德地图 · 本地距离兜底视图"，但**没有加载任何高德 JS SDK**。
- 真实 key 早已就绪：`frontend/.env.local` 内有 `VITE_AMAP_JS_KEY` 与 `VITE_AMAP_SECURITY_JS_CODE`。
- 后端配套的 `app/services/amap/{client,polyline,route_enhancement}` 在 unified-refactor 中被删除（仅剩 `__pycache__` 残留），所以真实路网 polyline 能力也一并丢失。

### 影响

地图是这类产品的第一观感。当前 mock 在评委追问"这是真实路线吗"时会露馅；站点相对位置因为是线性归一化，距离感也不准。

### 解决方案

采用**前端高德 JS API（@amap/amap-jsapi-loader）**，零后端改动即可拿到真实底图、标记与真实路网连线。

**1) 安装官方 loader 与类型：**

```bash
cd frontend
npm i @amap/amap-jsapi-loader
npm i -D @amap/amap-jsapi-types
```

**2) 暴露 env 变量类型** —— 在 `frontend/src/vite-env.d.ts` 追加：

```ts
interface ImportMetaEnv {
  readonly VITE_AMAP_JS_KEY: string
  readonly VITE_AMAP_SECURITY_JS_CODE: string
  readonly VITE_API_BASE_URL: string
}
```

**3) 新建加载 hook** `frontend/src/utils/amapLoader.ts`（示意骨架）：

```ts
import AMapLoader from "@amap/amap-jsapi-loader"

let amapPromise: Promise<typeof AMap> | null = null

export function loadAmap() {
  if (amapPromise) return amapPromise
  // 安全密钥必须在 load 之前挂到 window
  ;(window as any)._AMapSecurityConfig = {
    securityJsCode: import.meta.env.VITE_AMAP_SECURITY_JS_CODE
  }
  amapPromise = AMapLoader.load({
    key: import.meta.env.VITE_AMAP_JS_KEY,
    version: "2.0",
    plugins: ["AMap.Driving", "AMap.Walking"] // 真实路网连线用
  })
  return amapPromise
}
```

**4) 重写 `PlanMap.tsx`**（示意骨架，替换现有 mock）：

```tsx
import { useEffect, useRef } from "react"
import { loadAmap } from "../utils/amapLoader"
import type { RefinedPlan } from "../types/plan"

export function PlanMap({ plan, highlightedStopIndex, onStopClick }: PlanMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)

  useEffect(() => {
    let disposed = false
    loadAmap().then(AMap => {
      if (disposed || !containerRef.current) return
      const map = new AMap.Map(containerRef.current, { zoom: 12, viewMode: "2D" })
      mapRef.current = map
      // 高德坐标顺序为 [经度, 纬度]
      const path = plan.stops.map(s => [s.longitude, s.latitude] as [number, number])
      plan.stops.forEach((stop, i) => {
        const marker = new AMap.Marker({ position: path[i], label: { content: `${i + 1}` } })
        marker.on("click", () => onStopClick?.(i))
        map.add(marker)
      })
      // 方案 A：直线连接（最省事）
      map.add(new AMap.Polyline({ path, strokeColor: "#1677ff", strokeWeight: 5 }))
      // 方案 B：真实驾车路网（更真实，逐段 search，见下）
      map.setFitView()
    })
    return () => { disposed = true; mapRef.current?.destroy?.() }
  }, [plan.plan_id])

  return <div className="map-panel"><div ref={containerRef} className="real-map" /></div>
}
```

`.real-map` 在 `globals.css` 给一个固定高度（如 `min-height: 360px`），否则高德容器塌陷。

**连线两种取舍：**

- **方案 A（直线连接，推荐先做）**：用 `AMap.Polyline` 把站点依次连起来。最省事、零额外调用、和后端 solver 的"站点顺序"完全一致。
- **方案 B（真实路网 polyline）**：对每一段相邻站点调用 `AMap.Driving/Walking` 插件 `.search()` 渲染真实道路。更真实，但每段一次异步调用、并发与配额需控制。**建议 Demo 阶段先 A，行有余力再 B。**

> 若想把路网计算放后端（与 solver 的高德通行时间统一），可恢复被删的 `services/amap/polyline.py`（高德 Direction 返回的 `steps[].polyline` 解码为坐标串），由 `/api/plan/generate` 在每个 stop 上附带 `polyline` 字段，前端直接 `new AMap.Polyline({ path: decoded })`。这是中期优化，非 P0 必需。

### 验收标准

- 结果页地图为真实高德底图，N 个站点有编号标记，点击标记联动时间轴高亮。
- 站点间有连线；缩放/拖拽正常；`setFitView` 自动框选全部站点。
- 控制台无高德安全码报错（`INVALID_USER_SCODE` 等）。

---

## P0-2 · 接通并验证真实 AI / RAG / 高德链路

### 问题与证据

三大卖点在默认 Demo 下**一个都没真正跑过**，且失败是静默的：

- `app/llm/client.py`：`if not settings.llm_api_key: return fallback`，且 `except Exception: return fallback` —— 无 key 或调用异常时**静默**回退确定性解析，外部完全无感知。
- RAG：无 `EMBEDDING_API_KEY` 或未建 Chroma 索引 → 退化为关键词召回（`vector_repo`）。
- 高德：无 `AMAP_KEY` → haversine 估算。

### 影响

无法证明"AI 理解需求""语义召回""真实通行时间"真的有效；且静默兜底导致"明明配了 key 却没生效"难以排查。

### 解决方案

**1) 配置 key**（后端 `.env`，参照 `.env.example`）：

```bash
LLM_API_KEY=sk-...            # mimo / deepseek 等 OpenAI 兼容
EMBEDDING_API_KEY=sk-...      # 如 text-embedding-3-small
AMAP_KEY=...                  # 高德 Web 服务 key（注意与前端 JS key 不同）
```

**2) 构建语义索引**（一次性，配置 Embedding key 后）：

```bash
PYTHONPATH=backend python -m app.repositories.rag_index build --city hefei --reset
```

**3) 增加可观测性** —— 把静默兜底改为有日志、可上报。`app/llm/client.py` 的 `complete_json`：

```python
import logging
logger = logging.getLogger(__name__)

# ...
if not settings.llm_api_key:
    logger.info("LLM fallback: no api key configured")
    return fallback
try:
    ...
except Exception as exc:
    logger.warning("LLM call failed, using fallback: %s", exc)
    return fallback
```

同理在 `EmbeddingClient`（`app/llm/embedding.py`）与高德回退处（`app/solver/distance.py` 的 `estimate_transport`）各加一条 `logger.debug/info`，区分"真实命中"还是"兜底"。

**4) 健康检查兜底状态可见** —— `/health` 已返回 `get_rag_status()`（含 `collection_count`、`embedding_configured`）。可再加一个轻量 `GET /api/meta/integrations` 返回三项是否启用：

```python
{
  "llm": bool(settings.llm_api_key),
  "embedding": bool(settings.embedding_api_key),
  "amap": bool(settings.amap_key),
  "rag_collection_count": <chroma count>
}
```

**5) 真实链路冒烟验证脚本** `scripts/smoke_real_chain.py`（示意）：起服务后跑一次 `/api/plan/generate`，断言 intent 字段来自 LLM（而非 fallback 默认值）、候选 POI 的 `score_breakdown.semantic` 非零、transport mode 含 `transit/driving` 且 duration 来自高德。

### 验收标准

- `GET /health` 的 `rag.collection_count > 0` 且 `embedding_configured == true`。
- 配 key 后日志能看到"真实命中"而非 fallback。
- 同一 query 在"有 key / 无 key"下产出可见差异（意图字段、召回理由、通行时间）。

---

## P0-3 · 行程状态持久化

### 问题与证据

`app/services/state.py` 中 `POOL_REGISTRY / PLAN_REGISTRY / TRIP_REGISTRY / ...` 全是进程内 dict。`app/services/trip_service.py` 直接对 `TRIP_REGISTRY` 做 `.values() / .get() / [trip_id] = trip`。后端一重启，所有行程/方案/候选池全部丢失；多 worker 部署时各进程不共享。`config.py` 的 `DATABASE_URL`（postgres）与 compose 里的 postgres 服务当前**完全未被使用**。

### 影响

演示中途重启后端 = 用户行程全没；无法多实例部署。这是"Demo"与"产品"最本质的差距之一。

### 解决方案

**轻量优先**：用标准库 `sqlite3` 给"行程"这一关键持久实体落库（候选池/临时方案短生命周期，可暂留内存）。不引回 SQLAlchemy（已在 P1 移除），用 Pydantic 的 JSON 序列化最省事。

**1) 新建** `app/repositories/trip_store.py`（示意骨架）：

```python
import sqlite3
from pathlib import Path
from app.config import get_settings
from app.schemas.trip import TripRecord

class TripStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "./data/processed/app_state.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.execute(
                "create table if not exists trips ("
                " trip_id text primary key, user_id text, updated_at text, payload text)"
            )

    def _conn(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def get(self, trip_id: str) -> TripRecord | None:
        with self._conn() as con:
            row = con.execute("select payload from trips where trip_id=?", (trip_id,)).fetchone()
        return TripRecord.model_validate_json(row[0]) if row else None

    def list_by_user(self, user_id: str) -> list[TripRecord]:
        with self._conn() as con:
            rows = con.execute(
                "select payload from trips where user_id=? order by updated_at desc", (user_id,)
            ).fetchall()
        return [TripRecord.model_validate_json(r[0]) for r in rows]

    def upsert(self, trip: TripRecord) -> None:
        with self._conn() as con:
            con.execute(
                "insert into trips(trip_id,user_id,updated_at,payload) values(?,?,?,?)"
                " on conflict(trip_id) do update set user_id=excluded.user_id,"
                " updated_at=excluded.updated_at, payload=excluded.payload",
                (trip.trip_id, trip.user_id, trip.summary.updated_at.isoformat(),
                 trip.model_dump_json()),
            )
```

**2) 改 `trip_service.py`** —— 注入 store，替换三处 dict 操作：

- `__init__`: `self.store = TripStore()`
- `list_trips`: `return sorted([t.summary for t in self.store.list_by_user(user_id)], key=..., reverse=True)`
- `get_trip`: `return self.store.get(trip_id)`
- `save_route_version`: 把更新分支的 `TRIP_REGISTRY.get(...)` 换成 `self.store.get(...)`，结尾 `TRIP_REGISTRY[...] = trip` 换成 `self.store.upsert(trip)`。

> 注意：现有更新逻辑是"取出对象→`trip.versions.append(version)`→写回"。换成 store 后，`get` 返回的是反序列化的新对象，原地 mutate 后 `upsert` 即可，语义不变。

**3) 数据库文件** `app_state.sqlite` 走与 POI 库相同的 `data/processed/` 目录（compose 已挂载 `./data:/app/data`），无需额外卷。

> 如果团队更倾向 postgres（compose 已起），可把 `TripStore` 后端换成 psycopg + 同样的 `payload jsonb` 单表，接口不变。但 sqlite 对黑客松最省事。

### 验收标准

- 保存行程 → 重启后端 → `GET /api/trips/{id}` 仍返回该行程，版本历史完整。
- `GET /api/trips?user_id=...` 重启后仍列出历史行程。
- 既有 `test_trip_manager.py` 全绿（必要时让其用临时 sqlite 路径）。

---

## P0-4 · POI 数据体量核查与可复现

### 问题与证据

- 主路线硬约束要求：≥3 个 POI、含 1 个餐饮、含 1 个文化/娱乐/景点。若 `app_pois` 某类目在某"就近 + 小半径"组合下凑不齐，会频繁回退到 seed 兜底，路线质量下降。
- **数据分发问题**：`.gitignore` 第 11 行 `data/processed/*.sqlite` —— **`hefei_pois.sqlite` 不入版本库**。新克隆仓库的队友拿不到这份 POI 数据库，链路直接退化为 seed。仓库里有 `data/processed/ugc_hefei.jsonl`，但未见从 jsonl 重建 sqlite 的脚本。

### 影响

体量不足 → 路线常年兜底；不可复现 → 团队/部署环境数据不一致，"在我机器上是好的"。

### 解决方案

**1) 先体检**（确认体量与类目覆盖）：

```sql
-- sqlite3 data/processed/hefei_pois.sqlite
SELECT count(*) FROM app_pois;
SELECT category, count(*) c FROM app_pois GROUP BY category ORDER BY c DESC;
```

经验阈值：每个主要类目（餐饮/咖啡/景点/文化/娱乐/购物）在城内**至少 12–15 条**，主路线在多数 origin+半径下才不至于凑不齐。

**2) 解决可复现**（二选一）：

- **简单**：把 `hefei_pois.sqlite` 纳入版本库 —— 从 `.gitignore` 第 11 行排除该文件（如 `data/processed/*.sqlite` 改为 `data/processed/agent_sessions.sqlite` 单独忽略，保留 POI 库入库），或用 Git LFS。Demo 数据通常几 MB，直接提交最省心。
- **规范**：补一个 `scripts/build_poi_sqlite.py`，从 `ugc_hefei.jsonl`（+ 任何原始源）重建三表（`app_pois / poi_feature_index / ugc_evidence_index`），并在根 README 写明 `python scripts/build_poi_sqlite.py` 的复现步骤。`data/processed/README.md` 应描述三表 schema。

**3) 体量不足时的扩充**：补抓/导入更多合肥 POI 进 sqlite；或在 `solver_service._ensure_minimum_candidates` 的兜底里放宽半径（origin 半径内不足时按距离升序兜底全城 Top-N，已部分实现，可校核覆盖）。

### 验收标准

- 队友 clone 仓库后无需额外下载即可跑出非 seed 路线（数据入库或一键重建）。
- 主要类目体量达阈值；典型 query（如"下午少排队吃本地菜顺路拍照"）在默认/就近两种模式下都能产出含餐饮 + 文化/景点的合规主路线，不掉 seed。

---

## 落地顺序与里程碑

1. **P0-4**（半天）：体检 + 数据入库/可复现 —— 让后面所有验证都建立在真实数据上。
2. **P0-2**（半天～1 天）：配 key + 建索引 + 加日志/健康检查 —— 跑通并能证明真实链路。
3. **P0-1**（半天～1 天）：真实高德地图（先方案 A 直线连线）。
4. **P0-3**（1 天）：行程 sqlite 持久化 + 重启验证。

每完成一项，跑回归：

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
cd frontend && npm test -- --run && npm run build
```

## 验收总清单

- [ ] 地图为真实高德底图，标记 + 连线 + 联动正常，无安全码报错。
- [ ] `/health` 显示 RAG 索引非空、embedding 已配置；日志可区分真实命中 vs 兜底。
- [ ] 同一 query 在有/无 key 下产出可见差异。
- [ ] 重启后端后行程与版本历史不丢失。
- [ ] 队友 clone 后无需额外步骤即可跑出非 seed 路线。
- [ ] 后端 54+ 测试与前端测试/构建全绿。
