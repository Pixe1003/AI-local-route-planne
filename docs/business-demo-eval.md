# AIroute 业务 Demo 评测方案

本文用于区分“工程回归指标”和“业务 Demo 可用性”。工程指标继续由 `backend/eval/run_eval.py` 负责；业务 Demo 评测关注用户是否能在合肥本地生活场景里拿到可解释、可调整、可降级的路线建议。

## 评测场景

| 场景 | 输入重点 | 通过标准 |
| --- | --- | --- |
| 雨天室内 | 雨天、朋友、下午半日 | 室内类 POI 占主路线多数，理由提到雨天/室内稳定性 |
| 少排队本地菜 | 少排队、本地菜、顺路拍照 | 包含餐饮点，排队高风险点不应成为主推荐 |
| 临时换餐厅 | 在路线页输入“第二站换近一点的餐厅” | Agent 返回新 session，POI 顺序发生变化，地图或文字路线同步更新 |
| 预算紧 | 人均低预算 | 推荐总价不明显超过预算，超预算时有解释或替换 |
| 无高德 Key | 清空 Amap key 后生成路线 | `/api/agent/run` 返回 200，`route_chain=null`，但 `ordered_poi_ids` 和文字路线建议可用 |

## 业务指标

| 指标 | 目标 |
| --- | --- |
| UGC 覆盖率 | `/api/ugc/feed?city=hefei` 返回的卡片中 `source=simulated_ugc`，且覆盖餐饮、咖啡、文化/景点等多类目 |
| 推荐理由证据率 | 路线页每个主 POI 至少有结构化理由；有 UGC 证据时展示 evidence snippet |
| 天气影响可见性 | `weather_condition=rainy` 时，室内类 POI 得分或排序优于普通天气 |
| 反馈调整成功率 | 输入明确调整诉求后，返回的 POI 列表发生变化且页面同步 |
| 方案切换有效性 | 点击 Pareto 方案后，地图/文字路线使用该方案的 `ordered_ids` |
| 方案多样性 | `avg_variant_jaccard_overlap <= 0.65` 为理想目标；高于阈值时页面提示“候选受限，方案差异较小” |
| 品类丰富度 | `avg_category_entropy >= 1.0` 为理想目标，用于防止路线固定成“餐厅 + 咖啡 + 商场”模板 |
| 业务预期通过率 | `scenario_expectation_pass_rate` 覆盖雨天室内、少排队、预算紧等场景级规则 |
| 降级可用性 | 高德不可用时页面显示文字路线建议，不出现空白页或 Agent 失败 |

## 约束分层

`constraint_satisfaction_rate` 只代表工程合法性：必去/避开、营业时间、最少 POI、时间窗等硬约束不能失败。预算、排队、天气和距离默认作为业务护栏，通过打分惩罚、取舍说明和风险提示处理；只有用户明确表达“严格预算”“绝不排队”“必须室内”时才升级为硬约束。

## 手动验收步骤

1. 运行 `python scripts/generate_demo_ugc.py` 生成 `data/processed/ugc_hefei.jsonl`。
2. 可选运行 `python scripts/build_retrieval_index.py` 将 UGC evidence 写入 SQLite 派生表。
3. 启动后端和前端，打开首页，确认日期默认为当天、城市显示为合肥 Demo、天气选项可切换。
4. 选择“雨天”，生成路线，确认推荐理由偏向室内点。
5. 在路线页点击不同 Pareto 方案，确认站点和路线请求切换。
6. 清空高德 key 后重新生成，确认页面展示文字路线建议。
