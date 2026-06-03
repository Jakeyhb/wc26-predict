# WC26 Predict — 数据源合规与使用策略

> 最后更新：2026-06-04 | 版本：V1.7

---

## 核心原则

1. **公开输出不碰赔率**：所有 public_safe / creator_safe 输出不得包含赔率数字、博彩公司名称、投注术语。
2. **市场数据仅内部使用**：odds 类数据只在 internal_research shadow mode 中使用，用于模型校准研究。
3. **来源可追溯**：每条情报信号必须有 source_url 和 published_at。
4. **遵守上游许可**：每个数据源都有各自的使用条款，必须遵守。

---

## 数据源矩阵

| 数据源 | 用途 | public_safe | creator_safe | internal_research | 注意事项 |
|---|---|---|---|---|---|
| **FIFA 官方信息** | 赛程、球队、场馆、规则 | ✅ 是 | ✅ 是 | ✅ 是 | 标明来源 FIFA.com |
| **StatsBomb Open Data** | 历史事件数据（射门、传球等） | ⚠️ 有条件 | ⚠️ 有条件 | ✅ 是 | 遵守 Open Data License；需 attribution；不得再分发原始数据 |
| **football-data.org** | 赛程、比分、积分榜 | ⚠️ 有条件 | ⚠️ 有条件 | ✅ 是 | 遵守 API rate limit (10 calls/min)；遵守 terms |
| **football-data.co.uk** | 历史比赛结果 + 赔率 | ❌ 否 | ❌ 否 | ✅ 是 | 含博彩赔率数据，**仅限内部研究**；不得公开展示赔率字段 |
| **The Odds API** | 实时市场赔率（校准用） | ❌ 否 | ❌ 否 | ✅ 是 | **shadow mode only**；不存储原始赔率于公开输出中 |
| **API-Football (api-football.com)** | 比赛数据 + 赔率 | ❌ 否（赔率部分） | ❌ 否（赔率部分） | ✅ 是 | 基础 API 可用；odds endpoint 需 $15 addon；遵守 terms |
| **apifootball.com** | 比赛数据 + 赔率 | ❌ 否（赔率部分） | ❌ 否（赔率部分） | ✅ 是 | 基础 API 可用；odds endpoint 需 $15 addon |
| **Open-Meteo** | 天气数据 | ✅ 是 | ✅ 是 | ✅ 是 | 免费，无需 API key；标明来源 |
| **RSS / 公开新闻** | 新闻标题和摘要 | ✅ 摘要可展示 | ✅ 是 | ✅ 是 | 必须保留 source_url；不得全文转载 |
| **手动情报信号** | 伤病、停赛、阵容 | ✅ 摘要可展示 | ✅ 是 | ✅ 是 | 必须有 source_url + reviewer；标注 review_status |
| **GDELT Project** | 全球新闻元数据 | ⚠️ 有条件 | ⚠️ 有条件 | ✅ 是 | 免费版仅返回元数据，无正文 |

---

## 输出模式数据边界

### public_safe（公众可见）

**允许**：
- 比赛基本信息（球队、时间、场馆）
- 球队历史对阵记录
- FIFA 官方排名
- 教育性分析（战术、阵型、历史趋势）
- 来源化摘要（"据XXX报道，球员YYY可能缺席"）

**禁止**：
- 任何赔率数字（1X2、Asian Handicap、Over/Under 等）
- 博彩公司名称
- 投注术语（"盘口"、"水位"、"下注"等）
- 模型概率宣称（"胜率65%"）
- 命中率营销语言
- football-data.co.uk 原始数据
- The Odds API 数据
- 未审核的手动信号

### creator_safe（内容创作者）

在 public_safe 基础上额外**允许**：
- 数据溯源详情（"数据来源：football-data.org"）
- 模型不确定性说明（"本模型对冷启动球队置信度较低"）
- 赛后复盘数据（Brier/RPS 仅作为技术指标，不宣传命中率）

在 public_safe 基础上额外**禁止**：
- 赔率相关术语（同 public_safe）
- 将模型输出包装为"预测建议"

### internal_research（维护者/分析师）

**全部允许**，包括：
- 所有模型参数和概率
- 市场共识校准数据
- 赔率对比分析
- 原始数据导出

但**内部研究输出不得公开发布**。

---

## 数据存储安全

| 数据类型 | 存储位置 | 加密 | 备份 |
|---|---|---|---|
| 比赛结果 | SQLite/PostgreSQL | 否 | 是 |
| 模型参数 | model_artifacts/ | 否 | 是（Git LFS 或对象存储） |
| API 响应缓存 | 内存/磁盘 | 否 | 否 |
| 市场赔率 | SQLite (market_odds*) | 否 | 仅内部 |
| 情报信号 | SQLite (news_signals) | 否 | 是 |
| .env / API keys | .env.local | 文件系统权限 | **不入仓库** |

---

## 合规检查清单

发布公开内容前确认：

- [ ] 输出不含赔率数字（1X2、AH、O/U 等任何格式）
- [ ] 输出不含博彩公司名称
- [ ] 输出不含投注术语
- [ ] 输出不含模型概率宣称（public_safe 模式）
- [ ] 所有数据有可追溯来源
- [ ] 情报信号标注 review_status
- [ ] 不包含 football-data.co.uk 原始赔率数据
- [ ] 不包含 The Odds API 数据
- [ ] 已通过 `audit_public_outputs_no_odds.py` 扫描

---

## 参考

- [COMPLIANCE_AND_OUTPUT_POLICY.md](COMPLIANCE_AND_OUTPUT_POLICY.md) — 输出安全策略
- [MARKET_DATA_PROVIDER.md](MARKET_DATA_PROVIDER.md) — 市场数据提供商配置
- [CURRENT_STATUS.md](CURRENT_STATUS.md) — 当前项目状态
