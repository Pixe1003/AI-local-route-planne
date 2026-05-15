# 开发日志 - 2026-05-13

## 已完成内容

- 已接入合肥实际数据：结构化 POI 使用 `data/processed/hefei_pois.sqlite`，UGC 冷启动与证据检索使用 `data/processed/ugc_hefei.jsonl`。
- 已启用 LongCat tool-calling：模型为 `longcat-max`，OpenAI 兼容接口地址为 `https://api.longcat.ai/v1`。
- 已移除 agent `recommend_pool` 中的上海兜底逻辑：合肥池为空时不再静默查询上海，避免路线和地图结果回退到上海。
- 已取消前端 API 客户端的 30 秒请求超时，避免较长的 agent 路线生成被 axios 提前中断。
- 已修复高德地图 Marker 和 Polyline 不显示的问题：覆盖物现在会绑定到当前 map 实例，并等待地图 ready 后再绘制。
- 已替换过时的移动端 e2e：不再测试旧的“我的行程 / 新建行程 / 推荐池 / 上海”流程，改为当前 UGC 冷启动入口的 smoke test。
- 已修复本地 detached 启动脚本：脚本现在使用当前仓库路径，不再引用之前的临时工作目录。

## 已解决的问题

- 地图结果回退上海：原因是 `recommend_pool` 在目标城市没有默认候选时自动重试 `shanghai`，现已删除该回退。
- POI 和路线不显示：原因是 AMap 覆盖物创建后没有挂载到地图实例，现已修复。
- 请求过时或被取消：前端 axios 原先设置了 30 秒 timeout，现已改为不限制。
- 移动端 e2e 失败：原测试仍指向旧 UI 页面，现已对齐当前 UGC 首页和即时路线面板。
- 本地启动脚本不可复用：原脚本引用旧路径和旧 backend app-dir，现已改为相对当前仓库启动。

## 当前实际状态

- 后端默认城市：`hefei`。
- 前端主流程：UGC feed -> 即时路线面板 -> agent run -> 高德路线地图。
- Agent POI 选择逻辑：`recommend_pool` 只查询请求城市，不再做隐藏跨城市重试。
- 数据库查询逻辑：`PoiRepository` 从 `data/processed/hefei_pois.sqlite` 的 `app_pois` 加载 POI；`PoolService` 按 city 过滤、打分、取前 24 个候选、按类别分组，再生成 `default_selected_ids`。
- 默认 POI 选取逻辑：优先考虑用户收藏 POI，然后补入最佳餐饮点和最佳体验点，再用高分 POI 补足到最多 5 个，最后按就近顺序重排。
- LLM 决策逻辑：`Conductor` 会接收模型返回的合法 tool call；模型不可用或返回非法工具时，才回退到确定性工具链。

## 验证结果

```bash
set PYTHONPATH=backend
python -m pytest backend/tests/test_agent_minimal_flow.py backend/tests/test_llm_mimo_integration.py -q
# 9 passed

cd frontend
npm test -- src/__tests__/apiClient.test.ts src/__tests__/amapRouteMap.test.tsx
# 2 个测试文件通过，3 个测试通过

npm run build
# passed

npm run test:e2e
# 1 passed
```

## 保留说明

- 仓库中仍保留部分上海 seed 数据、旧 harness 和历史测试用例。它们属于历史演示/测试资产，本次没有直接删除。
- 如果后续要彻底迁移为“仅合肥版本”，建议单独做一次旧上海 fixture 和旧测试清理，避免影响当前已经能运行的主链路。
