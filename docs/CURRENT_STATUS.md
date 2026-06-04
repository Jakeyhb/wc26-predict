# WC26 Predict — 当前项目状态

> 这是项目唯一权威状态文件。所有其他文档如与本文档冲突，以本文档为准。
> 最后更新：2026-06-05 | 当前发布：V2.6 Enhanced

---

## 发布信息

| 字段 | 值 |
|---|---|
| Version | 2.6.0-enhanced |
| Tag | v2.6-enhanced |
| Build Name | V2.6 Enhanced — 实时数据 + LLM 分析 |
| 定位 | 本地 AI 增强分析工作台 — 模型预测 + 市场赔率 + 天气 + DeepSeek 内容生成 |
| 测试 | 118 passed |

## 包含范围

- Streamlit Local Dashboard（8 页面全中文）
- 4 模型融合预测引擎（DC + Enhancer + Elo + Pi）
- **市场赔率接入**（apifootball.com + The Odds API，15% 混合权重）
- **实时天气**（Open-Meteo 免费 API，13 个 WC26 场馆 + 智能猜测）
- **DeepSeek V4 Pro AI 分析**（赛前分析文章 + 视频口播脚本 + 多平台社交媒体文案）
- Artifact 推理架构（离线训练 → 本地加载 → 纯数学计算）
- FusionGraph（顺序融合 + 有效权重 + 模型分歧）
- 48 队硬事实校验 + 104 场 WC26 赛程
- Monte Carlo 赛事模拟器
- Creator Mode（AI 内容生成 + 模板回退）
- 只读 Database Explorer（三层防护）
- PowerShell 一键启动脚本
- Smoke test 自动验证

## V2.6 核心突破

1. **打破 V2.5 冻结** — 接通已实现的 70% 后端代码（市场、天气、LLM）
2. **prediction_enhanced.py** — 新编排层，包装 prediction_core + 实时数据源
3. **市场赔率融合** — 模型+市场线性混合（max 25%），VIP 去除 + 分歧检测
4. **DeepSeek 内容生成** — 三合一输出：分析文章 + 视频脚本 + 社媒文案
5. **优雅降级** — 任何实时数据源不可用时自动回退到基础 artifact 预测

## 排除范围（V2.6 不做）

- 实时首发阵容自动获取（API 暂不可用）
- 自动新闻爬取 + 信号提取（需 Event Registry key）
- 公开 SaaS 部署
- 新预测模型
- React / Next.js 前端重构
- 投注建议 / 原始赔率展示

## 架构护栏

详见 [`docs/ARCHITECTURE_GUARDRAILS.md`](ARCHITECTURE_GUARDRAILS.md)

## 版本历史

| 版本 | 核心突破 | 测试数 |
|---|---|---|
| V1.8 | WC26 数据结构 + CI 扩展 | 33 |
| V1.91 | 硬事实层 + 管线接口 | 42 |
| V2.0 | Artifact 推理 (937x 提速) | 42 |
| V2.2 | FusionGraph + 回测 + 模拟器 | 84 |
| V2.4 | Streamlit Dashboard + prediction_core | 91 |
| V2.5 | Local Demo Release — 收口冻结 | 91 |
| **V2.6** | **Enhanced — 实时数据 + LLM 分析** | **118** |
