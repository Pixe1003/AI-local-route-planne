# AIroute 业务 Demo 评测方案

本文用于区分“工程回归指标”和“业务 Demo 可用性”。工程指标由 `backend/eval/run_eval.py` 生成，用来防止核心链路回归；业务 Demo 评测关注用户在合肥本地生活场景中是否能拿到可解释、可调整、可降级、差异足够明显的路线建议。

最新中文评估报告见 `data/eval/route_eval_expanded_scenarios.md`。

---

## 评测范围

当前评测只覆盖合肥 Demo，不验证登录、下单、支付、优惠券、商家转化、多城市迁移和真实天气 API。UGC 使用 `scripts/generate_demo_ugc.py` 生成的演示数据，来源标记为 `simulated_ugc`。

---

## 场景集

| 场景 ID | 中文说明 | 检查重点 |
| --- | --- | --- |
| `budget_tight` | 低预算半日路线：80 元内、本地菜、避免高价点 | 低预算优先结构化召回；预算超出有惩罚或说明 |
| `family_rainy` | 雨天家庭室内路线：文化、咖啡、商场、节奏轻松 | 室内点占比、节奏稳定、理由提到天气影响 |
| `food_interleave_guardrail` | 餐饮穿插护栏：两餐之间加入文化或购物停留 | 餐饮不超过 2 个、不相邻、子品类不重复、路线距离不过长 |
| `half_day_food` | 半日本地美食：少排队、本地菜、顺路拍照 | 包含餐饮但不过度堆叠；排队风险可控 |
| `hot_budget_indoor` | 炎热低预算室内路线：轻餐、咖啡或商场、少通勤 | 炎热天气偏室内；低预算下不靠高价点凑分 |
| `low_queue` | 少排队效率路线：避开热门排队并包含午餐 | 平均排队时长低；午餐存在；餐饮节奏合理 |
| `must_visit` | 必去点路线：围绕城市博物馆补充餐饮和文化停留 | 必去/避开硬约束不被 Pareto 或修复步骤破坏 |
| `photo_cafe_culture` | 拍照咖啡文化路线：咖啡、文化和轻松餐饮组合 | 不把拍照/咖啡诉求退化成纯餐饮路线 |
| `rainy_parent_child_short` | 雨天亲子短路线：室内为主、含简餐、换乘短 | 室内比例、亲子节奏、品类丰富度、短通勤 |
| `shopping_dinner_evening` | 晚间购物晚餐路线：商场或文化开场，穿插不同餐饮 | 晚间可用、购物/文化与餐饮穿插、餐饮子类不重复 |

---

## 指标定义

| 指标 | 目标或解释 |
| --- | --- |
| `feasible_rate` | 每个场景都应返回 `ordered_poi_ids`，目标接近 1.0 |
| `constraint_satisfaction_rate` | 只代表硬约束合法性，目标不低于 0.9 |
| `explanation_faithfulness` | 推荐理由应能对齐 POI 属性或 UGC evidence，目标不低于 0.9 |
| `avg_route_variant_count` | 每场景至少 3 个，当前目标 5 个 |
| `avg_variant_jaccard_overlap` | Pareto 方案平均 POI 重叠度，目标不高于 0.65 |
| `avg_category_entropy` | 路线品类丰富度，目标不低于 1.0 |
| `avg_business_area_spread` | 商圈分散度，用来观察是否所有方案集中在同一片区 |
| `avg_soft_constraint_tradeoff_score` | 预算、排队、天气、距离护栏的综合取舍分 |
| `scenario_expectation_pass_rate` | 场景级业务预期通过率，gate 目标不低于 0.8 |
| `avg_latency_ms` | 从 Agent 工具链角度汇总的平均耗时；当前主要瓶颈在 `compose_story` |

---

## 最新结果

当前 10 场景评测 gate 通过，核心结果：

| 指标 | 最新值 |
| --- | ---: |
| `scenario_count` | 10 |
| `feasible_rate` | 1.0 |
| `constraint_satisfaction_rate` | 1.0 |
| `explanation_faithfulness` | 1.0 |
| `avg_latency_ms` | 约 5.9s |
| `avg_route_variant_count` | 5.0 |
| `avg_variant_jaccard_overlap` | 0.465 |
| `avg_category_entropy` | 1.006 |
| `avg_business_area_spread` | 0.583 |
| `avg_soft_constraint_tradeoff_score` | 0.824 |
| `scenario_expectation_pass_rate` | 0.8 |

当前未完全满足业务预期的点：

- `food_interleave_guardrail`：餐饮节奏符合要求，但有直线段距离偏长，说明地理紧凑性仍需要更强的替换/惩罚。
- `rainy_parent_child_short`：可行且室内占比高，但只有 3 站时品类熵偏低，雨天亲子场景需要更均衡的室内品类覆盖。

---

## 约束分层

`constraint_satisfaction_rate=1.0` 不等于业务效果满分。当前约束分三层：

| 层级 | 内容 | 评测含义 |
| --- | --- | --- |
| 硬约束 | 合肥范围、必去/避开 POI、营业关闭、至少 3 个 POI、时间窗不可超出 | 不满足则路线无效 |
| 业务护栏 | 预算、排队、天气、距离 | 默认做惩罚和解释，用户明确“严格”时才升级为硬约束 |
| 软偏好 | 本地菜、拍照、咖啡、文化、商场、慢节奏、少通勤 | 影响排序和理由，不直接决定合法性 |

因此业务评测必须同时看合法性和丰富度：合法性高只能说明“不出错”，多样性、节奏、通勤和取舍说明才能说明“像一个本地生活 Agent”。

---

## 手动验收步骤

1. 运行 `python scripts/generate_demo_ugc.py`，确认生成 `data/processed/ugc_hefei.jsonl`，且来源为 `simulated_ugc`。
2. 运行 `python scripts/build_retrieval_index.py`，确认 UGC evidence 能写入 SQLite 派生索引。
3. 启动后端和前端，打开首页，确认城市固定合肥、日期默认当天、天气选项可切换。
4. 选择“雨天”，生成路线，确认室内文化/商场/咖啡/娱乐权重更高，理由体现天气影响。
5. 输入低预算请求，确认低价结构化候选优先，且不会因 FAISS 冷启动阻塞 30s+。
6. 生成餐饮诉求路线，确认正式餐饮 POI 不超过 2 个，且中间穿插景点/文化/购物/娱乐。
7. 在路线页点击不同 Pareto 方案，确认地图、站点、耗时、距离、标签和取舍文案同步切换。
8. 清空高德 key 后重新生成路线，确认 `/api/agent/run` 返回 200，页面显示文字路线建议而不是空白错误页。
9. 在路线页继续对话，例如“第二站换近一点的餐厅”，确认返回的 POI 顺序发生变化，页面同步更新。

---

## 运行命令

```powershell
cd backend
python -m eval.run_eval --out ..\data\eval\route_eval_expanded_scenarios.md --enforce-gate
pytest tests/test_business_demo_readiness.py tests/test_constraint_diversity_balance.py tests/test_pool_retrieval_optimization.py -q
```
