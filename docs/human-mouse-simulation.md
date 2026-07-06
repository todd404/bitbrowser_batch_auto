# 人类鼠标行为模拟算法

## 背景

本项目在通过 BitBrowser + Playwright 自动执行页面流程时，常会触发滑块拼图、reCAPTCHA、hCaptcha、Cloudflare Turnstile、设备指纹等“人机验证”。许多反爬服务不只看是否点中按钮，还会采集鼠标轨迹的统计特征（速度峰值、加速度、曲率、停顿、抖动、点击间隔分布），用来区分机器与真人。

要在 flow 里稳定过这些验证，需要让 `page.mouse` 产生接近真人的运动学曲线与时间分布。本文档归纳公开的、被反复验证过的人类鼠标运动模型，作为本仓库 `human` 模块的理论依据，并指导 flow 作者在什么时候、用什么参数调用人类化动作。

文档面向两类读者：

- **flow 作者 / 外部 Agent**：看完后知道在 YAML / Python flow 里如何调用 `human_click`、何时该用人类化鼠标、参数怎么调。
- **仓库维护者**：知道 `src/bitbrowser_auto/human/mouse.py` 里每段算法对应哪条物理/工程模型，方便后续替换或调参。

实现优先级是“够用的真人感”而不是“完美复刻生理学”。所有模型都是公开的：Bézier 曲线、WindMouse、最小急动度（minimum-jerk）速度曲线、Fitts 定律、过冲修正、手部震颤噪声。没有任何从某个商业验证服务里逆向出来的私有参数。

---

## 一、为什么直线 `mouse.move(x, y, steps=N)` 不够用

Playwright 的 `page.mouse.move(x, y, steps=n)` 把起点到终点之间均匀插值 `n` 点。它存在的问题：

1. **轨迹是直线**。真人几乎从不走直线，鼠标路径总有曲率。
2. **速度恒定**。`steps=n` + 等间隔时间 → 匀速。真人是“起动—加速—减速—（可能过冲）—修正”。
3. **起止点不抖**。真人在目标处会停留并小幅震颤。
4. **跨调用无变异**。同一动作每次生成完全相同的轨迹，是最容易被指纹化的特征。
5. **点击与移动同帧**。真人移动到位后会有几十~几百毫秒的“决策停顿”再按下。

验证引擎采集到的就是这些“过于完美”的特征。本文接下来的每个算法都是用来打破其中一项。

---

## 二、算法清单

下面六条模型按“轨迹形状 → 速度曲线 → 时间预算 → 噪声 → 点击时序”的顺序串成一次完整的人类化移动。它们叠在一起用，分开看各自解决一个反爬特征。

### 2.1 Bézier 曲线：构造带曲率的路径骨架

把鼠标从起点 `A` 移到终点 `B`，先在它们之间生成 2~3 个随机控制点，再用三次或四次 Bézier 曲线把它们串成一条平滑曲线。控制点偏离 `A→B` 直线的幅度决定曲率，方向给一个随机偏角避免每次都往同一侧弯。

```
P(t) = Σ C(n, i) (1-t)^(n-i) t^i · P_i ,  t ∈ [0, 1]
```

要点：

- 控制点垂直于 `A→B` 方向的偏移量与距离 `|A→B|` 成正比（近距离小幅偏，远距离大幅偏），但有上下限。
- 距离很近（如 < 20 px）时退化为近似直线 + 少量抖动，避免出现“微米级抖动”。
- 每次调用重新随机控制点 → 跨调用天然不重复。
- 曲线本身只给出“形状”，还不涉及速度，所以需要配合 2.2 的 WindMouse 或 2.3 的最小急动度来分配走完曲线的节奏。

来源：Bézier 曲线是计算机图形学标准内容，自动化领域广泛用于鼠标轨迹（如历史项目 Benjamin阀门less/`.NET` 的 `BezierMice`、`Actiona`、`SikuliX` 等）。

### 2.2 WindMouse：在曲线骨架上加风扰动与逐步减速

WindMouse 是 Ben J 错写开源的一段经典伪代码，思路是：每一小步都把当前点朝目标方向“拉”，同时叠加一个随距离衰减的随机“风力”，越接近目标步长越小、抖动越小。它天然产出带噪声、带减速的轨迹，不需要预先解出整条曲线。

参数物理含义：

- `gravity` / `wind`：朝目标的拉力（gravity 直线收缩，wind 垂直漂移），二者随距目标远近被不同的随机扰动调制。
- `windMagic`：风力的随机幅度系数。
- `minStep` / `maxStep`：单步长度上下限，越接近终点 step 越小 → 减速。
- `targetNoise`：到点后还残留的小幅抖动。

WindMouse 的优势是“结束阶段有真实减速 + 末端抖动”，劣势是纯 WindMouse 路径不如 Bézier 平滑。本仓库采用**两层叠加**：先用 Bézier 生成主路径骨架，再用轻量 WindMouse 扰动每一段；既保平滑又保末端真实感。

来源：WindMouse pseudocode（Ben J，公开 wiki / 论坛流传）。它被多篇 RPA 模拟文献引用，参数空间广易于调参。

### 2.3 最小急动度（Minimum-Jerk）速度曲线：让全程速度像真人

人体手臂运动遵循“最小急动度”原则：在起点和终点速度、加速度均为零，且整条轨迹的急动度（位置三阶导）平方积分最小。解出的一维位置函数是 5 次多项式：

```
x(t) = x0 + (xf - x0) · (10τ³ - 15τ⁴ + 6τ⁵),   τ = t / T
```

它的速度形状是一条先升后降、峰值在中略偏后的钟形曲线。把 Bézier 路径按弧长参数 `s ∈ [0,1]` 排好，再用 `τ = t/T` 这一节律取点，就得到“平滑曲线 + 真人速度分布”的移动。比单纯按弧长均匀采样更接近真人。

要点：

- `T` 由 2.4 的 Fitts 定律决定。
- 在 `s` 空间用最小急动度 `f(τ)` 取点，再映射回 Bézier 路径上对应位置。
- 末端速度趋零，正好配合 2.5 的过冲修正。

来源：Flash & Hogan (1985)《The coordination of arm movements…》、Hogan (1984)，生物力学经典结论；机器人与 HCI 建模广泛采用。

### 2.4 Fitts 定律：预算整段移动的时间

Fitts 定律给出人类指向运动的总时长：

```
MT = a + b · log2(2D / W)
```

- `D`：移动距离（像素），起止点欧氏距离。
- `W`：目标宽度（点击区近似直径 / 距离阈值），可由元素 bbox 估算或给默认值。
- `a, b`：经验截距与斜率，正常人 `b ≈ 100~170 ms/bit`，`a ≈ 0~200 ms`。

把 `MT` 作为 2.3 的 `T`。远处的小目标自然移动久，近处大目标移动快——速度分布之外的第个真人特征“耗时合理”。可加全局 `speed_factor`（0.7~1.6）做个体差异。

来源：Fitts (1954)《The information capacity of the human motor system…》，HCI 标准模型。

### 2.5 过冲 + 修正（Overshoot & correction）

真人在小目标上常“冲过头再退一小步”。在 Bézier 路径末端追加一段：终点之外沿运动方向 5%~18% 距离处放一个“过冲点”，先走到那里（用较快的局部速度），停 60~180 ms，再用一小段慢速移动退回真实终点。概率化开启（如 45%），近距离大目标可不启用。

要点：

- 过冲距离随 `D` 缩放，有上限，避免飞出按钮。
- 过冲后停顿久一点更像“意识到偏了再纠”。
- 修正段用更小幅度 WindMouse 抖动。

### 2.6 手部震颤噪声（Tremor）

真人在目标停顿时并非完全静止。在到达目标后、点击前的若干帧里叠加 `N(0, σI)` 微抖动，`σ ≈ 0.3~1.5 px`，按 ~30Hz 抖动几帧。距离远 / 目标小 → σ 略小（更专注）；距离近 / 目标大 → σ 略大（更随意）。这一步很小但能打破“命中即瞬时按下”。

### 2.7 点击时序：决策停顿 + 按压停留

过验证的关键常在“移动结束到点击之间”的停顿与按下时长分布：

- **决策停顿**：移动到位后等 `40~260 ms`（短任务偏小，复杂页面偏大）再按下。
- **按压 dwell**：`mouse.down` 到 `mouse.up` 之间 `40~130 ms`，分布略右偏而非纯均匀。
- 即便用 Playwright 的 `page.mouse.click()`，也用手动 `down` + `sleep` + `up` 重建以控制 dwell。
- 连续点击之间加与上一次运动无关的随机间隔，避免固定节拍。

---

## 三、组合调用顺序（一次 `human_click` 内部）

```text
1. 读取目标元素 bbox → 中心点 (tx, ty) 与宽度 W
2. 当前指针位置 (cx, cy)（Playwright mouse 不暴露当前位置，由本模块自己跟踪）
3. 生成 2~3 个偏移控制点 → Bézier 路径
4. 对路径每段叠加轻度 WindMouse 扰动
5. Fitts 定律算总时长 T（含过冲预算）
6. 按最小急动度节奏沿路径采样，得到 N 个 (x, y, t)
7. 以这些点位调用 page.mouse.move(x, y)（每点间隔 ≈ t 增量，steps=1）
8. 概率化追加过冲点 + 停顿 + 修正段
9. 末端 tremor 抖动若干帧
10. 决策停顿 sleep
11. mouse.down() → dwell sleep → mouse.up()  ← 这才是“点击”
```

不需要过验证时可直接用 `human_move`（不含点击）。Python flow 里可调用 `from bitbrowser_auto.human.mouse import human_move, human_click` 直接驱动；declarative YAML flow 用 2.3 节描述的 `human_click` action。

---

## 四、本仓库内的集成点

新增 `src/bitbrowser_auto/human/__init__.py` 与 `src/bitbrowser_auto/human/mouse.py`，提供：

- `async def human_move(page, target, *, speed_factor=1.0, rng=None, ...) -> MoveResult`
- `async def human_click(page, selector=None, *, position=None, speed_factor=1.0, ...) -> ClickResult`
- `class CursorTracker`：记录“逻辑当前指针坐标”（Playwright `page.mouse` 不给出当前位置，需自行维护，初始随机一个安全区内位置）。
- 参数类 `MouseConfig`，集中 default + 上下界，方便 flow 失败后从 trace 里复现。

调用约束：

- 每个动作前若 URI 暴露的页面有 `mousemove` 监听，本模块产出的速度分布与曲率即可，无需 flow 作者干预。
- `human_click` 默认 `position='center'`，偏移到 bbox 内随机点而非几何中心（避免总点正中）。
- 失败时 trace 记录动作名、distance、duration、是否过冲，便于调参。

Declarative YAML 新增核心动作 `human_click`（也保留原 `click`）：

```yaml
- action: human_click
  selector: "button:has-text('登录')"
  speed_factor: 1.0          # 可选，默认 1.0，>1 更快
  overshoot: auto            # 可选 true/false/"auto"
  timeout_ms: 10000
```

`python_flow` 里可直接调用模块函数；不必经过 declarative allowlist。

`scripts/mouse_trace_parallel.py` 原本用机械圆/8字/锯齿路径驱动测试页，现改用 `human_move` 生成轨迹，使该脚本同时成为人类化鼠标的回归与可视化样本。

---

## 五、参数速查（默认值）

| 项 | 默认 | 范围 / 含义 |
|---|---|---|
| 控制点数 | 3 | 2~4 |
| 控制点偏移幅度 | 0.12·D | 上限 0.22·D，下限 ~8 px |
| Fitts a | 50 ms | 0~200 |
| Fitts b | 150 ms/bit | 100~170 |
| 目标宽 W | bbox 较短边 ∩ [16, 200] | — |
| speed_factor | 1.0 | 0.7~1.6 个体差异 |
| 过冲概率 | 0.45 | — |
| 过冲距离 | 0.07·D | ≤ 0.18·D |
| 过冲后停顿 | 60~180 ms | — |
| tremor σ | 0.6 px | 0.3~1.5 |
| tremor 帧数 | 4~8 | @~30Hz |
| 决策停顿 | 40~260 ms | — |
| 按压 dwell | 40~130 ms | 右偏分布 |

参数刻意不写死成“固定魔法常数”，并在 `MouseConfig` 里集中可调，所有随机量带种子入参便于复现失败案例。

---

## 六、使用建议

- 验证类页面（滑块、点选拼图、reCAPTCHA hCaptcha Turnstile）：用 `human_click`/`human_move`，`speed_factor` 偏低 (0.9~1.2)，开启过冲，tremor 中等。
- 普通业务点击（登录、翻页、加购）：可继续用 `click`；若后台有反爬采集，统一改 `human_click` 成本很低。
- 滑块拼图的特殊处理不在本算法覆盖范围：那是“按住 + 沿特定轨迹拖动到缺口”，需在 `human` 模块里额外提供 `human_drag`（按住期间持续抖动 + 末端微调），是新动作而非通用点击，留待扩展。
- 不要在同页面同时用两套生成器：若 flow 一处用 `human_click` 一处直接 `playwright mouse move`，前者产生的“真人轨迹”会被后者瞬时直线打断，反而更可疑。统一用一类。

---

## 七、参考资料（公开文献 / 经典实现）

- Flash T., Hogan N. (1985). *The coordination of arm movements: an experimentally confirmed mathematical model.* Journal of Neuroscience 5(7). —— 最小急动度模型。
- Hogan N. (1984). *An organizing principle for a class of voluntary movements.* Journal of Neuroscience 4(11). —— 同上理论支撑。
- Fitts P. M. (1954). *The information capacity of the human motor system in controlling the amplitude of movement.* Journal of Experimental Psychology 47(6). —— Fitts 定律原著。
- WindMouse pseudocode（Ben J，社区流传）。—— 风扰动 + 减速生成器。
- Bézier 曲线（计算机图形学标准，P. Bézier / P. de Casteljau，1960s）。
- Playwright `Mouse` API：`move(x, y, steps=)`, `down()`, `up()`, `wheel()` —— 本模块底层调用面。
- 已知工程实现（供阅读代码风格参考，非本仓库依赖）：`pyautogui` 移动模型、`Actiona`、`SikuliX` 的鼠标轨迹、各类社区 `human-mouse-move` Python 实现。

> 本环境在编写本文档时未能联网检索（搜索与抓取被环境策略阻断），以上模型为公开且被广泛复现的人因学与 RPA 工程结论，参数空间在五节给出。集成时建议在真实验证场景下用 `scripts/mouse_trace_parallel.py` 可视化比对，再回填 `MouseConfig` 默认值，把“本地数据上的最优解”固化下来。