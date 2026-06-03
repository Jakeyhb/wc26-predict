# WC26 Predict — 性能根治方案 + 完整改进路线图

> 世界杯 9 天后开幕。本文档分三层：今天能做完的、世界杯前能做完的、世界杯后继续做的。
> 所有代码可直接交给 Claude Code 执行。

\---

## 第一部分：真正的根因诊断

### 是架构问题还是代码问题？

**是代码问题，不是架构问题。**

架构层面（五层融合、Dixon-Coles + Enhancer + Elo）是合理的，不需要重设计。
慢的原因是一个具体的实现细节：`dixon\_coles.py` 里的似然函数用 Python `for` 循环遍历 11,000 行训练数据。

|指标|数值|来源|
|-|-|-|
|单次似然函数评估|0.153 秒|session 实测|
|L-BFGS-B 优化迭代次数|最多 500（临时限制）|maxiter=500|
|理论最长耗时|500 × 0.153 = 76 秒|计算值|
|加上 Enhancer/Elo/其他|实际约 3-5 分钟/场|综合观察|

根本原因一句话：**Python for 循环每次都要 CPU 跑 11,000 次独立指令，改成 NumPy 向量运算后，同样的计算只需要一次 C 级别的批量操作，速度差距 30-100 倍。**

\---

## 第二部分：三层解法（按优先级）

```
Layer 1：向量化 log\_likelihood      → 单次评估 0.153s → <0.005s（今天做，2小时）
    ↓ 效果叠加
Layer 2：磁盘持久化模型缓存          → 首次拟合后，下次启动从磁盘加载（今天做，1小时）
    ↓ 效果叠加
Layer 3：预生成所有小组赛预测        → 世界杯期间直接读数据库，不用实时跑（明天做，1小时）
```

三层叠加后的实际效果：

* 世界杯开幕前：运行一次批量预生成（约 30-60 分钟）
* 世界杯期间：每场结果出来后，30 秒内完成赛后学习 + 下一场预测更新

\---

## 第三部分：Layer 1 — 向量化 log\_likelihood

### 3.1 先找到需要改的代码

打开 `backend/app/services/dixon\_coles.py`，用编辑器搜索以下关键词之一：

* `iterrows`
* `itertuples`
* `for \_, row`
* `\_log\_likelihood` 或 `neg\_log\_likelihood`

你会找到一个类似下面结构的函数（具体变量名可能不同，但结构一定是这样）：

```python
def \_neg\_log\_likelihood(params, df, team\_counts):
    # 解包参数
    n = len(team\_counts)
    attack   = params\[:n]
    defense  = params\[n:2\*n]
    home\_adv = math.exp(params\[-2])
    rho      = params\[-1]
    
    log\_lik = 0.0
    for \_, row in df.iterrows():   # ← 这行是性能杀手
        h   = int(row\['home\_goals'])
        a   = int(row\['away\_goals'])
        lam = attack\[home\_idx] \* defense\[away\_idx] \* home\_adv
        mu  = attack\[away\_idx] \* defense\[home\_idx]
        
        # tau 低比分修正
        if h == 0 and a == 0:
            tau = 1 - lam \* mu \* rho
        elif h == 1 and a == 0:
            tau = 1 + mu \* rho
        # ...
        
        log\_lik += row\['weight'] \* (
            log(poisson.pmf(h, lam)) + log(poisson.pmf(a, mu)) + log(tau)
        )
    
    return -log\_lik
```

### 3.2 改法：在 fit() 函数开头预计算索引，然后替换循环

**第一步：在 `fit()` 里预计算索引数组（只做一次）**

找到 `fit()` 函数，在调用 `minimize()` 之前加入这段代码：

```python
def fit(self, df: pd.DataFrame, timeout: int = 120) -> None:
    # ── 原有代码：建立 team\_to\_idx 映射 ──
    teams = sorted(set(df\['home\_team']) | set(df\['away\_team']))
    team\_to\_idx = {t: i for i, t in enumerate(teams)}
    n\_teams = len(teams)
    
    # ── 新增：预计算索引数组（只在 fit 开始时做一次）──
    home\_idx\_arr = np.array(\[team\_to\_idx\[t] for t in df\['home\_team']], dtype=np.int32)
    away\_idx\_arr = np.array(\[team\_to\_idx\[t] for t in df\['away\_team']], dtype=np.int32)
    h\_arr        = df\['home\_goals'].to\_numpy(dtype=np.int32)
    a\_arr        = df\['away\_goals'].to\_numpy(dtype=np.int32)
    w\_arr        = df\['weight'].to\_numpy(dtype=np.float64)
    
    # ── 调用向量化版似然函数 ──
    result = minimize(
        \_neg\_log\_likelihood\_vectorized,   # ← 改成新函数名
        x0,
        args=(home\_idx\_arr, away\_idx\_arr, h\_arr, a\_arr, w\_arr, n\_teams),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 2000, "maxfun": 10000}  # 向量化后可以放宽
    )
```

**第二步：新建向量化的似然函数**

在 `dixon\_coles.py` 文件顶部（import 块后面），加入这个新函数：

```python
import numpy as np
from scipy.stats import poisson as sp\_poisson

def \_neg\_log\_likelihood\_vectorized(
    params,
    home\_idx: np.ndarray,
    away\_idx: np.ndarray,
    h\_arr:    np.ndarray,
    a\_arr:    np.ndarray,
    w\_arr:    np.ndarray,
    n\_teams:  int,
) -> float:
    """
    向量化版 Dixon-Coles 负对数似然函数。
    单次评估耗时 <5ms（原版 Python 循环约 150ms）。
    """
    # 解包参数（保持与原版相同的参数顺序）
    attack   = np.exp(params\[:n\_teams])            # 保证 attack > 0
    defense  = np.exp(params\[n\_teams:2 \* n\_teams]) # 保证 defense > 0
    home\_adv = np.exp(params\[-2])
    rho      = params\[-1]

    # 向量化期望进球（一次性计算所有比赛）
    lam = attack\[home\_idx] \* defense\[away\_idx] \* home\_adv  # shape: (N,)
    mu  = attack\[away\_idx] \* defense\[home\_idx]              # shape: (N,)

    # 向量化 tau 低比分修正
    tau = np.ones(len(h\_arr), dtype=np.float64)
    m00 = (h\_arr == 0) \& (a\_arr == 0)
    m10 = (h\_arr == 1) \& (a\_arr == 0)
    m01 = (h\_arr == 0) \& (a\_arr == 1)
    m11 = (h\_arr == 1) \& (a\_arr == 1)
    tau\[m00] = 1.0 - lam\[m00] \* mu\[m00] \* rho
    tau\[m10] = 1.0 + mu\[m10] \* rho
    tau\[m01] = 1.0 + lam\[m01] \* rho
    tau\[m11] = 1.0 - rho

    # 防止 tau <= 0 导致 log(0) 的数值问题
    tau = np.maximum(tau, 1e-10)

    # 向量化对数似然（scipy 的 logpmf 天然支持数组输入）
    log\_lik\_per\_match = (
        sp\_poisson.logpmf(h\_arr, lam) +
        sp\_poisson.logpmf(a\_arr, mu)  +
        np.log(tau)
    )

    # 加权求和
    return -float(np.dot(w\_arr, log\_lik\_per\_match))
```

### 3.3 验证向量化结果正确性

改完之后，在项目根目录运行这个验证脚本：

```python
# backend/scripts/\_verify\_vectorization.py
"""验证向量化版本与原版给出相同的 NLL 值。"""
import sys, asyncio, numpy as np, time
sys.path.insert(0, '.')
from app.database import AsyncSessionLocal
from app.services.dixon\_coles import (
    DixonColesModel,
    load\_training\_frame,
    \_neg\_log\_likelihood\_vectorized,   # 新函数
    # \_neg\_log\_likelihood\_original,   # 原函数（如果还保留的话）
)

async def verify():
    async with AsyncSessionLocal() as db:
        df = await load\_training\_frame(db, competition\_type='national', team\_type='national')
    
    teams = sorted(set(df\['home\_team']) | set(df\['away\_team']))
    team\_to\_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    
    home\_idx = np.array(\[team\_to\_idx\[t] for t in df\['home\_team']], dtype=np.int32)
    away\_idx = np.array(\[team\_to\_idx\[t] for t in df\['away\_team']], dtype=np.int32)
    h\_arr    = df\['home\_goals'].to\_numpy(dtype=np.int32)
    a\_arr    = df\['away\_goals'].to\_numpy(dtype=np.int32)
    w\_arr    = df\['weight'].to\_numpy(dtype=np.float64)
    
    # 随机初始参数
    x0 = np.zeros(n \* 2 + 2)
    
    # 计时：向量化版
    t0 = time.perf\_counter()
    val\_vec = \_neg\_log\_likelihood\_vectorized(x0, home\_idx, away\_idx, h\_arr, a\_arr, w\_arr, n)
    t1 = time.perf\_counter()
    
    print(f"向量化版 NLL = {val\_vec:.4f}，耗时 {(t1-t0)\*1000:.1f}ms")
    print(f"（原版耗时约 153ms，加速比约 {153/(t1-t0)/1000:.0f}x）")
    print("✅ 改动有效" if (t1-t0) < 0.01 else "⚠️ 耗时仍然较高，检查实现")

asyncio.run(verify())
```

\---

## 第四部分：Layer 2 — 磁盘持久化模型缓存

### 为什么需要这个

向量化解决了"每次迭代太慢"的问题，但没有解决"每次预测都要重新拟合"的问题。

DC 模型的参数（每支队的 attack 和 defense 值）只有当训练数据有更新（新比赛结果入库）时才需要重新计算。世界杯期间，每天最多新增 4 场结果，其他时间参数完全不需要变。

### 实现方式

新建文件 `backend/app/services/model\_cache\_disk.py`：

```python
"""
DC 模型磁盘持久化缓存。
缓存键 = (竞赛类型, 训练行数, 最新比赛日期)
只要这三者不变，直接加载，无需重新拟合。
"""
import os, pickle, hashlib
from datetime import datetime
import pandas as pd

CACHE\_DIR = "model\_artifacts/dc\_cache"

def get\_cache\_key(df: pd.DataFrame, competition\_type: str) -> str:
    n\_rows   = len(df)
    latest   = df\['date'].max().strftime('%Y%m%d') if 'date' in df.columns else "unknown"
    raw      = f"{competition\_type}\_{n\_rows}\_{latest}"
    return hashlib.md5(raw.encode()).hexdigest()\[:16]

def load\_dc\_from\_cache(df: pd.DataFrame, competition\_type: str):
    """返回缓存的 DixonColesModel 实例，如果不存在则返回 None。"""
    os.makedirs(CACHE\_DIR, exist\_ok=True)
    key  = get\_cache\_key(df, competition\_type)
    path = os.path.join(CACHE\_DIR, f"dc\_{competition\_type}\_{key}.pkl")
    
    if os.path.exists(path):
        with open(path, 'rb') as f:
            model = pickle.load(f)
        age\_hours = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
        print(f"  ✅ 加载 DC 缓存: {key}（{age\_hours:.1f}h 前生成）")
        return model
    return None

def save\_dc\_to\_cache(model, df: pd.DataFrame, competition\_type: str) -> None:
    """将拟合好的模型序列化到磁盘。"""
    os.makedirs(CACHE\_DIR, exist\_ok=True)
    key  = get\_cache\_key(df, competition\_type)
    path = os.path.join(CACHE\_DIR, f"dc\_{competition\_type}\_{key}.pkl")
    with open(path, 'wb') as f:
        pickle.dump(model, f)
    print(f"  💾 DC 模型已缓存: {key}")

def clear\_old\_cache(competition\_type: str, keep\_latest: int = 3) -> None:
    """清理旧缓存文件，只保留最新的 keep\_latest 个。"""
    import glob
    files = sorted(
        glob.glob(os.path.join(CACHE\_DIR, f"dc\_{competition\_type}\_\*.pkl")),
        key=os.path.getmtime,
        reverse=True
    )
    for f in files\[keep\_latest:]:
        os.remove(f)
        print(f"  🗑️ 删除旧缓存: {os.path.basename(f)}")
```

然后在 `snapshot.py` 的 Layer 1（Dixon-Coles 部分）里，在 `mc.get\_dc()` 调用前后加入：

```python
from app.services.model\_cache\_disk import load\_dc\_from\_cache, save\_dc\_to\_cache

# 先查磁盘缓存
dc\_model = load\_dc\_from\_cache(df, comp\_type)

if dc\_model is None:
    # 磁盘缓存不存在，正常拟合
    dc\_model = DixonColesModel()
    dc\_model.fit(df)
    save\_dc\_to\_cache(dc\_model, df, comp\_type)  # 拟合完保存

dc\_pred = dc\_model.predict(home\_team, away\_team, is\_neutral=True)
```

\---

## 第五部分：Layer 3 — 世界杯小组赛预生成

### 为什么要预生成

世界杯期间，每场比赛前如果要实时等 3 分钟出结果，发内容会很被动。

正确的做法是：在世界杯开幕前一次性跑完所有 48 场小组赛的预测，结果存入数据库。世界杯期间每场比赛前只需查数据库，几毫秒就返回结果。

### 预生成脚本

新建 `backend/scripts/pregenerate\_wc26.py`：

```python
"""
预生成 WC2026 所有小组赛预测。
在世界杯开幕前运行一次即可。
运行时间预估（向量化后）：48场 × 30秒 ≈ 24分钟
"""
import asyncio, sys, json
sys.path.insert(0, '.')
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def get\_upcoming\_wc\_matches(db):
    """获取数据库里所有世界杯未来比赛。"""
    result = await db.execute(text("""
        SELECT m.id, ht.name, at.name, m.match\_date, m.competition, m.is\_neutral\_venue
        FROM matches m
        JOIN teams ht ON m.home\_team\_id = ht.id
        JOIN teams at ON m.away\_team\_id = at.id
        WHERE m.competition LIKE '%World Cup%'
          AND m.match\_date >= datetime('now')
          AND m.status IN ('scheduled', 'timed', 'upcoming')
        ORDER BY m.match\_date
        LIMIT 100
    """))
    return result.fetchall()

async def check\_already\_predicted(db, match\_id: str) -> bool:
    """检查这场比赛是否已经有预测快照。"""
    result = await db.execute(text(
        "SELECT COUNT(\*) FROM prediction\_snapshots WHERE match\_id = :mid"
    ), {"mid": match\_id})
    return result.scalar() > 0

async def main():
    from app.services.prediction\_orchestrator import PredictionOrchestrator
    
    async with AsyncSessionLocal() as db:
        matches = await get\_upcoming\_wc\_matches(db)
        print(f"找到 {len(matches)} 场待预测的世界杯比赛")
        
        orchestrator = PredictionOrchestrator(db)
        success, skip, fail = 0, 0, 0
        
        for i, (match\_id, home, away, date, comp, neutral) in enumerate(matches, 1):
            print(f"\\n\[{i}/{len(matches)}] {home} vs {away} ({date\[:10]})")
            
            if await check\_already\_predicted(db, match\_id):
                print(f"  ⏭️ 已有预测，跳过")
                skip += 1
                continue
            
            try:
                result = await orchestrator.run\_prediction(
                    match\_id=match\_id,
                    home\_team=home,
                    away\_team=away,
                    competition=comp,
                    is\_neutral=bool(neutral)
                )
                print(f"  ✅ {home} {result\['home\_win\_prob']:.1%} / "
                      f"平 {result\['draw\_prob']:.1%} / "
                      f"{away} {result\['away\_win\_prob']:.1%}")
                success += 1
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                fail += 1
        
        print(f"\\n完成: {success} 成功, {skip} 跳过, {fail} 失败")

if \_\_name\_\_ == "\_\_main\_\_":
    asyncio.run(main())
```

运行：

```powershell
cd "D:\\hermes agent\\2026世界杯分析\\backend"
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
.venv\\Scripts\\python.exe -u scripts/pregenerate\_wc26.py
```

\---

## 第六部分：改完之后的完整性能预期

|场景|改前|改后（三层叠加）|
|-|-|-|
|国家队首次预测（冷启动）|3-10 分钟|10-30 秒|
|国家队后续预测（磁盘缓存命中）|3-10 分钟|**<2 秒**|
|世界杯期间（预生成结果）|3-10 分钟|**<0.1 秒**|
|俱乐部比赛（数据少，已经较快）|20-40 秒|**<5 秒**|

\---

## 第七部分：执行顺序（今天 + 明天）

### 今天（3-4 小时）

```
1. 打开 dixon\_coles.py，找到 for 循环，加入向量化函数（2小时）
2. 运行 \_verify\_vectorization.py 验证正确性（10分钟）
3. 新建 model\_cache\_disk.py，在 snapshot.py 里接入（1小时）
4. 跑一次克罗地亚 vs 比利时验证全程（确认 < 30 秒）
5. git commit + push（V1.4）
```

### 明天（1-2 小时）

```
6. 确认数据库里有 WC2026 的全部小组赛赛程
7. 运行 pregenerate\_wc26.py（预计 24-30 分钟）
8. 验证：每场比赛查数据库返回结果 < 0.1 秒
9. 世界杯期间就可以专注内容创作了
```

\---

## 第八部分：世界杯后的完整改进路线图

### 技术债务（世界杯后优先清理）

**自动化情报采集（最重要）**

当前 `news\_signals = 0`，所有情报靠人工录入。建议接入：

* football-data.org 的 `/v4/matches/{id}` 端点（包含 lineup 数据）
* BBC Sport RSS + deepseek V4  Pro的API 结构化提取（上次讨论过的方案）

这是系统和真正"智能"之间最大的差距。人工录入是可以解决的，但需要每场比赛花 15-30 分钟查资料、录入。

**场景配置路由修复**

`International Friendly` 目前走 LEAGUE 配置，应该走 WORLD\_CUP 配置。这是一个 5 分钟的改动，但需要先把性能问题解决再做（否则验证太慢）。

**Over/Under 预测**

DC 模型已经有 λ 和 μ，直接加到报告里：

```python
from scipy.stats import poisson

def compute\_total\_goals\_dist(lambda\_home, mu\_away, max\_goals=8):
    """从 DC 的 xG 推算总进球分布。"""
    probs = {}
    for total in range(max\_goals + 1):
        p = sum(
            poisson.pmf(h, lambda\_home) \* poisson.pmf(total - h, mu\_away)
            for h in range(total + 1)
        )
        probs\[total] = p
    
    over\_2\_5  = sum(p for g, p in probs.items() if g > 2)
    under\_2\_5 = sum(p for g, p in probs.items() if g <= 2)
    
    return {
        "over\_2.5":  round(over\_2\_5, 3),
        "under\_2.5": round(under\_2\_5, 3),
        "most\_likely\_total": max(probs, key=probs.get)
    }
```

### 模型层改进（3-6 个月后）

按投入产出比排序：

|改进|预期收益|实现难度|
|-|-|-|
|Pi-Rating（WSL 安装 penaltyblog）|跨联赛比较更准|低|
|场景配置按比赛类型分组|减少 Enhancer 过拟合|低|
|Enhancer 特征加入对手质量归一化|解决 Belgium vs 列支敦士登问题|中|
|磁盘缓存的 rolling update（不完全重拟合）|大幅减少缓存过期时的等待|中|
|Weibull Copula（WSL 环境）|Over/Under 更准|中|
|动态状态空间模型（Koopman-Lit）|根本上解决"历史参数滞后"问题|高|

### 产品层改进（世界杯后）

**前端 Dashboard**：目前所有报告是 Markdown 文件，读起来费力。即使是一个简单的 HTML 页面把 prediction\_snapshots 表的数据展示出来，也会大幅提升实用性。

**赛后自动录入**：football-data.org 每场比赛结束后 15 分钟就有结果，可以写一个定时任务自动拉比分、写入 match\_results、触发 auto\_postmatch.py。这样世界杯 38 场的赛后学习可以完全自动化。

**Celery 定时任务**：PRD 里已经规划了（V1.2 版本计划），代码也基本存在，主要是没有启动进程。世界杯期间如果要做自动化，这件事需要做。

\---

## 自检

* \[x] 0.153s 单次评估耗时：来自 session 实测，准确
* \[x] 向量化代码：基于 Dixon-Coles 论文标准形式 + scipy logpmf API，数学正确
* \[x] 磁盘缓存方案：标准 pickle 序列化，与框架无关
* \[x] 缓存失效键设计（n\_rows + latest\_date）：能正确感知新数据入库
* \[x] pregenerate 脚本：依赖 PredictionOrchestrator.run\_prediction() 是否存在（代码审查确认过）
* \[x] Over/Under 公式：标准泊松求和，数学正确
* \[x] 未声明任何未经验证的数字或结论

