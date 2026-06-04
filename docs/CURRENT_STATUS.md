# WC26 Predict — 当前项目状态

> 这是项目唯一权威状态文件。所有其他文档如与本文档冲突，以本文档为准。
> 最后更新：2026-06-04 | 当前发布：V2.5 Local Demo Release

---

## 发布信息

| 字段 | 值 |
|---|---|
| Version | 2.5.0-local-demo |
| Tag | v2.5-local-demo |
| Build Name | V2.5 Local Demo Release |
| 定位 | 本地可展示 MVP — 个人使用 + 录屏 + 内容验证 |
| 测试 | 91 passed |

## 包含范围

- Streamlit Local Dashboard（8 页面全中文）
- 4 模型融合预测引擎（DC + Enhancer + Elo + Pi）
- Artifact 推理架构（离线训练 → 本地加载 → 0 token 预测）
- FusionGraph（顺序融合 + 有效权重 + 模型分歧）
- 48 队硬事实校验 + 104 场 WC26 赛程
- Monte Carlo 赛事模拟器
- Creator Mode（录屏 + 社交媒体文案）
- 只读 Database Explorer（三层防护）
- PowerShell 一键启动脚本
- Smoke test 自动验证

## 排除范围（V2.5 不做）

- 实时伤病/首发/天气/赔率动态调整
- 公开 SaaS 部署
- 登录系统 / 多人权限
- 新预测模型
- React / Next.js 前端重构
- LLM 直接调整概率
- 投注建议 / 赔率展示

## 架构护栏

详见 [`docs/ARCHITECTURE_GUARDRAILS.md`](ARCHITECTURE_GUARDRAILS.md)

## 72 小时冻结规则

V2.5 发布后 72 小时内只允许：
- 修启动失败
- 修页面崩溃
- 修明显文案/合规错误

禁止新增功能、新模型、新页面、架构重构。

## 版本历史

| 版本 | 核心突破 | 测试数 |
|---|---|---|
| V1.8 | WC26 数据结构 + CI 扩展 | 33 |
| V1.91 | 硬事实层 + 管线接口 | 42 |
| V2.0 | Artifact 推理 (937x 提速) | 42 |
| V2.2 | FusionGraph + 回测 + 模拟器 | 84 |
| V2.4 | Streamlit Dashboard + prediction_core | 91 |
| V2.5 | Local Demo Release — 收口冻结 | 91 |
