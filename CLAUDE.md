# CLAUDE.md — WC26 Predict (Claude Code 执行规则)

## 1. Project Goal

足球比赛预测系统，核心闭环：

1. **赛前多源数据融合** — 历史比赛、球队/球员状态、新闻信号、天气、赔率
2. **概率预测引擎** — Dixon-Coles + Enhancer + κ-Elo + Pi-Rating，融合输出胜平负概率
3. **赛后富数据复盘** — 技术统计、比赛事实、预测偏差、信号归因
4. **Replay-based learning** — 权重和数据源可靠性调整必须通过 replay/backtest gate，不允许无证据自动改权重

## 2. Claude Code Role

Claude Code 的职责边界：

- **只负责** coding ticket 的实现、测试、验证
- **不负责** 最终审查自己产出的 diff（审查由 Hermes Agent 另行执行）
- **不写** Hermes Agent 的职责、监督流程或 PR 审查规则
- **不输出** APPROVE / REQUEST_CHANGES / COMMENT 等审查判定
- Claude Code is the implementer, not the reviewer

## 3. Execution Rules

每次交互必须遵守：

- **每次只执行一个 ticket**，不跨 phase
- **编辑前必须先进入 plan mode**（除非是单文件单行 typo fix）
- **用户明确确认后才能修改文件**（plan mode 内）
- **不做未请求的大规模重构** — 严格按 ticket scope 修改
- **不删除未知文件** — 任何文件删除必须先盘点用途
- **不提交 secrets、.env、token、API key** — 包含这些内容的文件不得出现在 commit 中
- **不承诺投注收益、不输出赌博建议** — 合规硬边界

## 4. Verification Rules

每个 ticket 完成后必须输出：

1. **Files changed** — 修改了哪些文件，每个文件的变更目的
2. **Commands run** — 运行了哪些验证命令（完整命令行）
3. **Test output** — 测试输出摘要（pass/fail 数量，失败明细）
4. **Known limitations** — 已知限制和未覆盖的边界条件
5. **Next suggested ticket** — 建议的下一个 ticket

**严格禁止**:
- 将测试失败包装成成功
- 用 "看起来正常" 代替实际命令输出
- 跳过测试声称完成
- 检查失败但退出码为 0

## 5. Data Degradation Rules

外部数据源不可靠是常态，必须显式处理：

- **外部数据抓取失败时** — 必须记录失败原因（`logger.warning(..., exc_info=True)`）
- **不允许静默降级** — 调用方必须知道某个数据源本次不可用
- **degraded_reasons 必须保留** — 预测结果中 `degraded_reasons` 字段不得在 pipeline 中途被清空
- 缺失数据必须写入 `missing_data` 或 equivalent 字段，不得悄悄跳过

## 6. Weight / Model Rules

模型权重和安全边界：

- **不允许直接修改生产权重** — `weights.py` 中的生产配置只能通过代码审查合入
- **权重变化必须通过 replay/backtest gate** — 候选权重必须在 replay harness 上验证后才可提交
- **学习闭环先产出候选建议（candidate update）** — 不自动覆盖生产配置
- 任何权重变更 PR 必须附带：before/after 数值对比 + backtest 证据 + 变更理由

## 7. Stop Condition

- **完成一个 ticket 后停止** — 不自动推进到下一个 ticket
- **等待用户确认** — 用户 review 当前 ticket 产出后再给下一个 ticket
- 如果 ticket 失败，停止并报告失败原因和诊断建议
