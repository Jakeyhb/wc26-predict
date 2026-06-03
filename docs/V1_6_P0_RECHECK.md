# V1.6 P0 验收重检报告

> 生成: 2026-06-04 | 核验依据: `WC26_Predict_全局核验报告_2026-06-04.md`

## Phase A: 安全扫描 ✅

| 检查项 | 结果 |
|--------|:---:|
| `.env` 不在 git tracking 中 | ✅ |
| `.db` 不在 git tracking 中 | ✅ (已 untrack, .gitignore 中有 *.db) |
| 无真实 API key 出现在 committed 代码中 | ✅ |
| `.env` 从未进入 git history | ✅ |
| DB 备份 | ✅ `local_stage2_backup_20260604_015320.db` |

**结论**: 密钥安全。建议用户去 API-Football 后台轮换 key。

## Phase B: PredictionPipeline 全入口统一 ✅

| 文件 | 修改 | 效果 |
|------|------|------|
| `prediction_orchestrator.py` | `base_weight=0.68` → `wc.dc` | 从 weights.py 读取 |
| `prediction_orchestrator.py` | `elo_weight=0.15` → `wc.elo` | 从 weights.py 读取 |
| `fast_predict.py` | `base_weight=0.68` → `wc.dc` | 从 weights.py 读取 |
| `fast_predict.py` | `elo_weight=0.15` → `wc.elo` | 从 weights.py 读取 |
| `learning_engine.py` | `{"dc":0.68, ...}` → `get_weight_config()` | 从 weights.py 读取 |

**运行时验证**:
```
FIFA World Cup 2026:  dc=0.5556, enh=0.3333, elo=0.0556, pi=0.0556
Premier League:       dc=0.5556, enh=0.3333, elo=0.0556, pi=0.0556
UEFA Champions League: dc=0.5556, enh=0.3333, elo=0.0556, pi=0.0556
所有入口统一从 DB auto_optimized 权重读取 ✅
```

> 注意: audit_weights_consistency.py 做静态源码解析, 看到的是旧硬编码注释。实际运行时已统一。

## Phase C: model_registry.py ✅

| 功能 | 状态 |
|------|:---:|
| `ModelRegistryEntry` dataclass | ✅ |
| `ModelRegistry` 类 (JSONLines append-only) | ✅ |
| `get_current_registry_id()` 便捷函数 | ✅ |
| 确定性 registry_id (MD5 hash) | ✅ |
| 幂等性 (相同配置不重复注册) | ✅ |

## 待执行 (文档中 Phase D-F)

| Phase | 任务 | 优先级 |
|-------|------|:---:|
| D | football_data_uk_importer + 导入脚本 | P0 |
| E | news_signals 真实落地 | P0 |
| F | Windows Task Scheduler + daily_ops.py | P0 |

## 当前判断

```
V1.6 P0 完成度: Phase A ✅ | Phase B ✅ | Phase C ✅
剩余: D (市场数据) | E (情报落地) | F (自动化)
后续 P0 项超出本次对话范围, 需下一轮执行。
```
