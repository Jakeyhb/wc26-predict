# ⚽ WC26 — 一个球迷的 AI 分析工具

> 2001 年出生，从 2010 年开始看球。2026 年 3 月接触 AI 编程，零基础自学，在 Claude Code 的帮助下做了一个世界杯比赛分析程序。

---

## 📊 这是什么

输入两支球队，程序会输出一份分析报告，包含：
- 四层数学模型融合的分析结果
- 进球期望与比分分布
- Elo 实力评分排名
- 近期战绩与形势

**它不是"预测"，是"分析"** —— 数学统计 + AI 辅助，结果仅供参考和娱乐。

---

## 🏗️ 怎么做的

```
数据采集 → 分析引擎 → 结果输出
  │              │              │
  ├─ football-data.org    ├─ Dixon-Coles 泊松模型    ├─ Markdown 分析报告
  ├─ StatsBomb Open      ├─ Tabular Enhancer (HGB)  ├─ Win/Draw/Loss 概率
  ├─ openfootball        ├─ κ-Elo 评分系统          ├─ 比分分布
  ├─ Open-Meteo          └─ Pi-Rating               ├─ Over/Under
  └─ 手动情报注入                                    └─ Elo 排名
                              ↓
                    赛后自动复盘 → 自我学习闭环
```

---

## 🚀 快速开始

```bash
# 1. 安装后端依赖
cd backend
pip install -r requirements.txt

# 2. 启动 API 服务
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. 跑一场分析
python scripts/snapshot.py --home "Brazil" --away "Argentina" --competition "World Cup 2026" --neutral

# 4. 启动前端（可选）
cd ../apps/web && npm install && npm run dev
```

访问 `http://127.0.0.1:5173` 查看 Web 界面。

---

## 🔧 技术栈

| 层次 | 技术 | 用在哪 |
|------|------|--------|
| 后端 | Python + FastAPI | API 服务 |
| 数据 | SQLite / PostgreSQL | 历史比赛存储 |
| 前端 | React 18 + Vite + Tailwind | Web 界面 |
| AI | DeepSeek (API) | 新闻抽取、文章生成 |
| 分析 | Dixon-Coles + HGB + κ-Elo | 比赛分析引擎 |

---

## 📈 数据规模

- **16,000+** 场历史比赛（football-data.org + openfootball + StatsBomb）
- **440+** 支球队（国家队 + 俱乐部）
- **48 支** 2026 世界杯参赛队完整赛程
- **154 次** 分析快照积累
- **48 次** 赛后复盘评估

---

## 🎯 分析引擎 v2.0

四层模型融合，按比赛场景动态调整权重：

| 模型 | 类型 | 世界杯权重 |
|------|------|-----------|
| Dixon-Coles | 泊松进球模型 | 55.6% |
| Tabular Enhancer | 梯度提升 (37 特征) | 33.3% |
| κ-Elo 评分 | 评分系统 | 5.6% |
| Pi-Rating | 零均值进球差 | 5.6% |

每次分析后自动记录，赛后对比真实结果进行复盘学习。

---

## 📂 目录结构

```
backend/          # FastAPI + 分析引擎 + 脚本
  app/
    main.py       # API 入口
    services/     # 预测引擎核心
    routers/      # API 路由
  scripts/
    snapshot.py   # 单场分析入口
  data/
    local_stage2.db   # SQLite 数据库
apps/web/         # React 前端 (11 个页面)
packages/shared/  # 共享类型定义
```

---

## ⚠️ 免责声明

**这是一个个人学习项目，所有分析结果仅供娱乐参考，不构成任何建议。**

- 本项目不提供也不涉及任何投注、博彩、赌博相关内容
- 不显示任何赔率数字，不推荐任何博彩平台
- 分析结果基于历史统计数据，不保证准确性
- 缺失关键实时数据（首发阵容、伤病情报），结果可能显著偏离实际

**享受比赛本身，这才是足球的意义。⚽**

---

## 📝 许可证

MIT — 随便用、随便改，GitHub 上见到请给个 ⭐

---

*一个球迷 + 一台电脑 + 世界杯 = 这个项目 · 2026*
