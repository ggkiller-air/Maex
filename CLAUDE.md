# CLAUDE.md (Maex)

本文件给在 `Maex/` 内工作的 Claude Code 实例提供工作目标与开发约束。Maex 的常规架构 / runner / suite / 方法对照见 `Maex/README.md` 与 `Maex/智能体网关短期记忆初步对接文档.md`,本文件**只描述当前的核心工作:把 LightWM 接入 Maex**。

> 关联文档:
> - 容器级总览:`/root/Project/AgentGateway/CLAUDE.md`
> - LightWM 架构 / spec 文件布局:`/root/Project/AgentGateway/LightWM/CLAUDE.md`
> - 整体方案图:`/root/Project/AgentGateway/pipeline_picture/LMW_Maex.jpg`

---

## 当前核心任务:LightWM → Maex Minimal Verify Test

### 背景与目标

学长主导的 LightWM(ESSA 显式状态短期记忆框架)已在 ALFWorld 上跑通。当前阶段要把 LightWM 接入 Maex 的 COHERENT benchmark(多智能体:quadrotor / robot_dog / robot_arm)。整体方案已基本通过 `LMW_Maex.jpg`,但**在投入完整工程化(Oracle、离线归纳、batch 评测)之前**,需要先做一个 minimal verify test —— 证明 LightWM 的 `ESSAAgent` 能在 Maex 的 env / observation / action 形态下成功跑完一个任务。

### 关键决策(已与学长对齐,2026-05-20)

1. **schema 来源:跳过离线归纳,人工预先写死 specs**
   - 不跑 `LMW_Maex.jpg` 顶部的 Frontier LLM 离线归纳 + 人工 review 流程
   - 不跑 online schema 总结
   - 直接基于 `Maex/env/data/env0.json` 的本体词汇(node category / properties / states、agent class、`task_goal` 谓词、admissible commands)**人工编写** `Maex/memory/ESSA/task_specs.json` 和 `Maex/memory/ESSA/subtask_specs.json`
   - 等价于把图上的 offline 归纳产物预先固化成静态文件

2. **Oracle 处理:verify 阶段不实现,改用静态 base_subtask_sequence**
   - `LMW_Maex.jpg` Bottom Panel 第 2 框的 Oracle(LLM dispatch 下一个 `{agent_class, agent_id, subtask_type, args}`)**本期不做**
   - 沿用 ESSA 在 ALFWorld 的做法:每个任务类型在 `task_specs.json` 里写死一个 `base_subtask_sequence`,Agent 顺序遍历
   - verify 通过后再补 Oracle

3. **代码归属:所有新代码 / specs / runner 写在 `Maex/` 内**
   - 方便统一走 Maex git 提交
   - LightWM 当作只读依赖,通过 `from LightWM.agent.ESSAAgent import ESSAAgent` 等方式引用
   - 不要修改 `LightWM/` 下任何文件(若发现 LightWM 必须改才能接入,先停下来和学长 / 用户确认)

4. **难度梯度路线**(首发 → 后续扩展)
   - **首发(必须先跑通)**:`env0.json` task 0 —— quadrotor 降落到 high kitchen table,`gt_steps=5`。单 agent、单 subtask,最简单。
   - **第二档**:task 3 —— silver coin + battery 入 box,`gt_steps=4`。多物体单房间,触发 robot_arm pick&place subtask。
   - **第三档**:task 2 —— bread→plate + milkbox→microwave,`gt_steps=5`。多 agent、含 open/close microwave、跨容器。
   - 后续视情况再向 env1~env4 扩展。
   - 每加一档,优先评估当前 specs / MaexObserver 是否需要**扩展**,而不是直接重写。

### Claude 启动目录

**强烈建议在 `~/Project/AgentGateway` 启动**,而不是 `~/Project/AgentGateway/Maex`。原因:
- 需要同时读 LightWM 源码(`ESSAAgent`、`BaseEnvObserver` 接口、spec 字段约定)和写 Maex 代码
- 在 AgentGateway/ 下跑 python 时,`from LightWM.* import` 和 `from maex.* import` 都能自然 resolve(都是 sibling package)
- 文件依然写入 `Maex/` 下,不影响 git 仓库归属

### 预计开发拆解(按依赖顺序)

1. **Schema 规划**(本步骤,人工完成,不写代码)
   - 列出 env0.json task 0 涉及到的 entity 类型(quadrotor、high kitchen table、room、floor、door)
   - 设计 macro `task_state` 字段:agent 位置、agent 状态(LAND/FLY)、目标 receptacle、子任务进度
   - 设计 subtask 类型清单(首发只需 1-2 个,例如 `navigate_and_land`)
   - 设计每个 subtask 的:`input_para` / `output_para` / `caller_mapping` / `subtask_status_schema` / `patch_ops_policy.allowed` / `executor_sys_rules`
   - 输出:`Maex/memory/ESSA/task_specs.json` + `Maex/memory/ESSA/subtask_specs.json` 草案

2. **`MaexObserver` 实现**
   - 在 `Maex/env/coherent/` 下新建,实现 `LightWM.env.base.BaseEnvObserver` 协议的 4 个方法
   - `extract_state_patch`:把 Maex 的 obs(scene graph)翻译成 ESSA `subtask_state` 的 patch ops
   - `normalize_action` / `detect_action_verb` / `get_full_action_space`:对接 Maex 的 action 集合

3. **Minimal runner**
   - 在 `Maex/` 内新建一个 minimal entry(例如 `examples/minimal_essa_verify.py`)
   - 装配:`ESSAAgent(env_observer=MaexObserver(), task_specs=..., subtask_specs=...)` + env0 task 0
   - 单任务跑完即算 verify pass

4. **跑通 task 0 → 扩展到 task 3 → 扩展到 task 2**

### 开发约束(高优)

- **不要**给 Maex 引入 `LightWM/` 之外的新依赖,除非确实必要
- **不要**绕过 schema 设计直接 hack 一个 if-else dispatch —— minimal verify 的目的就是证明 ESSA 的结构化 state + spec 驱动的 subtask 真的能跑,如果绕过这个核心机制就失去验证意义
- **不要**修改 LightWM 任何文件
- 每完成一步先和用户对齐再继续,不要一口气写到底
