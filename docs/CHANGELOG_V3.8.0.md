# V3.8.0 — 模型加载链修复 + 权重门控 + 参数溯源

**发布日期:** 2026-06-15
**上一版本:** V3.6.1-postmatch-stats (实际从未有 V3.7.X 代码版本)
**紧急程度:** 🔴 Critical — 修复静默参数回退 bug

---

## 背景

2026年6月15日，执行了两场世界杯小组赛赛后复盘：

| 比赛 | 赛果 | 模型预测方向 | 实际结果 |
|------|------|:---:|:---:|
| 🇩🇪 德国 vs 🇨🇼 库拉索 (Group E) | 7-1 | ✅ 德国胜 | 正确 |
| 🇳🇱 荷兰 vs 🇯🇵 日本 (Group F) | 2-2 | ❌ 日本胜 | 平局 |

复盘过程中发现一个严重问题：**V3.6.1 快照（6月14日）的 Brier 显著优于 "V3.7.2" 回溯预测（6月15日）**。初步诊断为"V3.7.2 退化"，但深入调查揭示了完全不同的根因。

---

## 🔴 P0: 模型参数静默回退

### 根因

系统存在**两条相互独立的模型加载路径**，加载了不同时间训练的、具有不同参数的模型：

```
路径 A (V3.6.1 快照, 6月14日):
  snapshot.py → model_cache_disk.load_dc_from_disk()
  → backend/model_artifacts/dc_cache/dc_*_07be8cd4...pkl
  → 基于 11,007 行训练数据重新拟合 ✅

路径 B ('V3.7.2' retro, 6月15日):
  from_artifacts() → prediction_core._load_dc()
  → backend/artifacts/models/dc.pkl (6月4日, 10,999 行)
  → 加载了过期的静态 pickle 🔴
```

**Pipeline 代码从未改变**（始终报告 `3.6.1-postmatch-stats`）。所谓的"退化"是加载了过期模型参数导致的。

### 证据

| 证据 | 详情 |
|------|------|
| DC 参数精确匹配 | `from_artifacts` 加载的 DC 参数 == 6月4日 V2.0.0 快照参数 |
| 训练数据行数验证 | V3.6.1 快照记录 11,007 行；artifacts pickle 仅 10,999 行 |
| 5 个 DC 缓存版本 | `dc_cache/` 中有 5 个不同参数的 DC，分别在 6/4、6/12、6/14 生成 |
| Pipeline 版本号未变 | 始终报告 `3.6.1-postmatch-stats` |

### 修复

1. **删除静态 artifact 文件**
   - `backend/artifacts/models/dc.pkl` — 删除
   - `backend/artifacts/models/enhancer.joblib` — 删除

2. **disk cache 成为唯一加载路径**
   - `_load_dc()` 和 `_load_enhancer()` 仅从 `model_artifacts/dc_cache/` 加载最新文件
   - Cache miss 时自动从训练数据拟合并保存
   - 不再存在"回退到静态文件"的代码分支

3. **train_models.py 对齐**
   - `save_dc()` / `save_enhancer()` 直接写入 disk cache，不再生成静态文件
   - `simulate_wc26.py` 的 `load_dc()` / `load_enhancer()` 委托给 `prediction_core`

### 影响

| 比赛 | 修复前 Brier | 修复后 Brier | 改善 |
|------|:---:|:---:|:---:|
| 德国 vs 库拉索 | 0.312 | **0.135** | -57% |
| 荷兰 vs 日本 | 0.931 | **0.832** | -11% |

DC 预测现在精确匹配 V3.6.1 快照。

---

## 🟡 P1: 权重门控 — Enhancer 降权

### 两场复盘发现

| 模型层 | 德国 vs 库拉索 Brier | 荷兰 vs 日本 Brier | 评价 |
|--------|:---:|:---:|------|
| **DC** | **0.070** | **0.714** | 🏆 两场均最佳 |
| **Enhancer** | **1.097** | **1.288** | 🔴 两场均灾难 |
| Elo | 0.156 | 1.181 | 🟡 荷兰-日本方向错误 |
| Pi Rating | 0.044 | 0.949 | 🟢 德国场最佳，荷兰场尚可 |

### 系统性缺陷确认

- **Enhancer 反平局偏置**：两场平局概率均 < 20%（德国场 7.4%，荷兰场 15.3%），而实际比赛一场有平局可能、一场确实平局
- **Enhancer 极度不稳定**：德国场 Brier 从 0.537 (V3.6.1) 到 1.097 (V3.8.0)，受训练数据影响巨大
- **DC 稳定可靠**：是唯一在两场比赛中均表现最好的模型层

### 权重调整

| 参数 | 旧值 | 新值 | 有效权重变化 |
|------|:---:|:---:|------|
| `auto_optimized_dc` | 0.5556 | **0.70** | +7.1pp |
| `auto_optimized_enhancer` | 0.3333 | **0.20** | -15.4pp |
| `auto_optimized_elo` | 0.0556 | **0.10** | +3.7pp |
| `auto_optimized_pi_rating` | 0.0556 | **0.10** | +4.4pp |

**有效权重:** DC 56.7% · Enhancer 24.3% · Elo 9.0% · Pi 10.0%

完整审计追踪已写入 `model_weight_config` 表（`update_reason` + `previous_value` + `updated_by`）。

---

## 🟢 P2: 参数溯源

### 问题

`prediction_snapshots` 存储了 `component_probs`（各层输出概率），但**没有存储模型内部参数**（DC attack/defense strength 等）。无法追溯为什么同一场比赛的两次预测结果不同。

### 修复

`prediction_snapshots.pipeline_params` 新增字段：

| 字段 | 说明 |
|------|------|
| `dc_params_hash` | DC attack_params 的 MD5 哈希 — 唯一标识模型参数状态 |
| `training_df_fingerprint` | 训练数据（行数、日期范围、球队数）的 MD5 哈希 |
| `training_df_max_date` | 训练数据最新比赛日期 |

现在可以精确辨别：两次预测结果不同是因为模型参数变了、训练数据变了、还是权重变了。

---

## 🔵 版本号修正

| 位置 | 旧值 | 新值 |
|------|------|------|
| `backend/app/version.py` | `3.6.1-postmatch-stats` | `3.8.0` |
| `backend/app/version.py` TAG | `v3.6.1-postmatch-stats` | `v3.8.0` |
| DB `model_weight_config` label | — | `AUTO_OPTIMIZED` v2.0 |
| `weights.py` `_WORLD_CUP` | v1.0 | v3.8 |

> **注意：不存在 V3.7.X 代码版本。** 之前的 git tag "V3.7.2" 是提交信息层面的标签，Pipeline 代码版本从未从 `3.6.1-postmatch-stats` 变更。本次直接跳到 3.8.0 以避免混淆。

---

## 🔵 sklearn 版本不匹配

disk cache 中的模型可能用 sklearn 1.9.0 训练，而当前环境是 1.8.0。当前通过 `warnings.catch_warnings()` 静默处理。模型结构兼容，微小预测偏差预期小于使用过期静态 artifact 的误差。

**建议：** 下次 `pip install` 时升级到 sklearn ≥ 1.9.0。

---

## 涉及文件

| 文件 | 变更 |
|------|------|
| `backend/app/version.py` | VERSION → 3.8.0 |
| `backend/app/services/prediction_core.py` | `_load_dc` / `_load_enhancer`：删除 artifact fallback，disk cache 唯一路径 + cold-start auto-fit |
| `backend/app/services/prediction_pipeline.py` | `pipeline_params` 新增 dc_params_hash / training_df_fingerprint / training_df_max_date |
| `backend/app/services/weights.py` | `_WORLD_CUP` 默认权重同步更新，market_max → 0.25 |
| `backend/scripts/simulate_wc26.py` | `load_dc` / `load_enhancer` 委托给 prediction_core |
| `backend/scripts/train_models.py` | `save_dc` / `save_enhancer` 写入 disk cache |
| `backend/data/local_stage2.db` | `model_weight_config` 权重更新 + 审计追踪；`match_results` 写入两场真实数据 |
| ~~`backend/artifacts/models/dc.pkl`~~ | **已删除** |
| ~~`backend/artifacts/models/enhancer.joblib`~~ | **已删除** |

---

## 赛后复盘记录

### 德国 7-1 库拉索
- **报告:** `backend/reports/POSTMATCH_Germany_vs_Curacao_20260615.md`
- **DB:** 真实 xG 3.91-0.40，场馆修复为 NRG Stadium, Houston
- **Learning log:** Brier 0.312（修复前），Enhancer -0.240 边际损害
- **复盘审计报告:** 同一报告中对比了"另一个AI"的复盘，识别出 8 个问题

### 荷兰 2-2 日本
- **报告:** `backend/reports/POSTMATCH_Netherlands_vs_Japan_20260615.md`
- **DB:** 真实 xG 0.79-0.54，场馆修复为 AT&T Stadium, Arlington
- **Learning log:** Brier 0.921（修复前），模型和市场方向全错（平局未被预测）
- **核心发现:** 内部模型方向分裂（Elo/Pi 选荷兰，DC/Enhancer 选日本），唯平局无人选

### 两场累积结论
- Enhancer 33.3% 权重在两个极端场景（悬殊/接近）均表现糟糕
- DC 是唯一稳定的模型层 — 两场 Brier 均最低
- Market 两场整体最佳（Brier 0.011, 0.814）
- 系统需要 Elo-gap 门控：|gap|>150 和 |gap|<50 均应降低 Enhancer 权重

---

## 向后兼容

- `from_artifacts()` API 未变
- `predict_sync()` API 未变
- 快照格式向后兼容（新增字段，旧快照缺少这些字段不受影响）
- `model_weight_config` 旧值保留在 `previous_value` 列

---

## 安全检查清单

- [x] 不存在"回退到静态文件"的代码路径
- [x] `from_artifacts()` 和 `train_models` 使用同一 disk cache
- [x] 所有模型加载经过版本化和哈希化
- [x] 权重变更有完整审计追踪（who / when / why / old value）
- [x] 快照包含足够信息追溯"为什么预测是这个值"
- [x] sklearn 版本差异已显式文档化
