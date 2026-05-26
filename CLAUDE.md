# WC26 Predict — Claude Code 工作手册

## 项目路径
`D:\hermes agent\2026世界杯分析\`

## 这个项目是什么
足球比赛预测分析系统。核心价值：
1. 用数学模型（Dixon-Coles + Enhancer + κ-Elo）预测比赛概率
2. 用Claude API生成每场比赛的深度分析报告
3. 赛后自动复盘，学习哪里预测错了

## 技术栈（不要改变）
- 后端：Python + FastAPI，SQLite数据库
- 前端：React 18 + TypeScript + Vite + Tailwind CSS
- 数据库：SQLite位于 backend/data/local_stage2.db
- 预测脚本：backend/scripts/snapshot.py（可直接调用）

## 项目结构
backend/           # FastAPI后端
  app/
    main.py        # FastAPI入口
    routers/       # API路由
    services/      # 预测引擎服务
  scripts/
    snapshot.py    # 核心预测脚本
    sync_results.py
  data/
    local_stage2.db  # SQLite主数据库
apps/web/          # React前端
  src/
    pages/         # 页面组件
    lib/api.ts     # API调用层

## 数据库核心表
- matches：5989场比赛（含2026世界杯赛程）
- match_results：5798场赛果（含xG）
- teams：232支球队
- prediction_snapshots：61条预测历史
- postmatch_eval：47条赛后评估

## 已知问题清单（不要在今天修复这些）
- news_signals始终为0（接受，不修复）
- Celery任务（不要动）
- market_odds（不要动）
- 任何新的数据库表（不要新建）

## 今天只做三件事
1. 修复前端API连接（从mock数据改为真实后端数据）
2. 导入openfootball国际赛数据（国家队训练数据128→2000+场）
3. 添加Claude API分析生成功能

## 合规边界（严格遵守）
- 不显示任何赔率数字
- 不提供投注建议
- 不提任何博彩平台名称
