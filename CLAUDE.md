# CLAUDE.md (Maex)

本文件给在 `Maex/` 内工作的 Claude Code 实例提供工作目标与开发约束。Maex 的常规架构 / runner / suite / 方法对照见 `Maex/README.md` 与 `Maex/智能体网关短期记忆初步对接文档.md`,本文件**只描述当前的核心工作:把 LightWM 接入 Maex**。

> 关联文档:
> - 本仓库内:`Maex/README.md`(Maex 常规架构 / runner / 方法对照)、`Maex/智能体网关短期记忆初步对接文档.md`(短期记忆对接节奏)
> - 仓库外(参考,需绝对路径访问):
>   - `/root/Project/AgentGateway/CLAUDE.md` —— 容器级总览
>   - `/root/Project/AgentGateway/pipeline_picture/LMW_Maex.jpg` —— 整体方案图
>   - `/root/Project/AgentGateway/LightWM/CLAUDE.md` —— LightWM 上游设计文档,**Maex vendor 的那部分代码的设计依据**(算法字段语义、spec 消费点),修 ESSA 相关 bug 时可参考

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

3. **代码归属:Maex 自包含,LightWM 算法核心已 vendor 进 `Maex/`**(2026-05-25 完成)
   - 所有新代码 / specs / runner 写在 `Maex/` 内,统一走 Maex git 提交
   - LightWM 的 `ESSAAgent` / `BaseEnvObserver` / ESSA prompts 已 vendor 进:
     - `Maex/agent/essa_agent.py`(算法本体)
     - `Maex/env/lightwm_base.py`(observer 协议)
     - `Maex/prompt/essa_prompts.py`(prompt 模板生成器)
   - **Maex 不再依赖 sibling `LightWM/` 目录** —— `grep 'from LightWM\|import LightWM' Maex/` = 0 匹配
   - 上游 `LightWM/` 仍是 vendored 代码的**设计文档来源**,改 ESSA 算法 / spec 消费逻辑时可参考 `LightWM/CLAUDE.md` 和原始源码,但不再自动同步上游

4. **Spec 单位:per task family,不是 per task instance**(2026-05-20 修正)
   - LightWM `task_specs.json` 的一条 entry 就是 **task family** 级别(参见 ALFWorld 的 `pick_and_place_simple` / `pick_heat_then_place_in_recep` 等),一份 spec 自动覆盖该 family 下所有实例 —— 目标物 / 容器 / 房间这些差异由 `caller_mapping` 把实例参数冻结到 `memory` 来吸收。
   - **本期 verify family**:`land_on_receptacle` —— quadrotor 单 agent、goal predicate `on_<quadrotor>_<receptacle>`、无载货
   - **Representative instance**:env0 task 0(quadrotor 降落到 high kitchen table,`gt_steps=5`)。env0 内还有 task 1 也属于这个 family,可用于 spec 跑通后做"同 family 不同实例"的健壮性验证。
   - **其它 family 等 land_on_receptacle 跑通后再识别**。不要试图一次性覆盖 env0 全部 21 个任务 —— 写 spec 时按需扩展 family 表。
   - env0 task family 划分有一份**未验证的 Claude 草稿**(覆盖 5 个 family),保存在 user-level memory(`env0-task-family-draft.md`),**当前不作为执行依据**。

### Claude 启动目录

**在 `~/Project/AgentGateway/Maex` 启动即可**(2026-05-25 起)。理由:
- Maex 现在自包含 —— `from agent.essa_agent import ESSAAgent` / `from env.lightwm_base import BaseEnvObserver` / `from prompt.essa_prompts import ...` 等 import 仅依赖 `Maex/` 在 `PYTHONPATH` 上,不再需要 sibling `LightWM/`
- 跨仓库参考(LightWM 上游源码、AgentGateway 父级文档)可用绝对路径访问 `/root/Project/AgentGateway/LightWM/...`,不影响日常 cwd

> 历史:2026-05-25 之前,推荐的 cwd 是 `~/Project/AgentGateway`,因为当时 `from LightWM.* import` 依赖 sibling 解析。vendor 迁移之后此约束已消失。

### 预计开发拆解(按依赖顺序)

1. **Schema 规划**(本步骤,人工完成,不写代码)
   - 列出 env0.json task 0 涉及到的 entity 类型(quadrotor、high kitchen table、room、floor、door)
   - 设计 macro `task_state` 字段:agent 位置、agent 状态(LAND/FLY)、目标 receptacle、子任务进度
   - 设计 subtask 类型清单(首发只需 1-2 个,例如 `navigate_and_land`)
   - 设计每个 subtask 的:`input_para` / `output_para` / `caller_mapping` / `subtask_status_schema` / `patch_ops_policy.allowed` / `executor_sys_rules`
   - 输出:`Maex/memory/ESSA/task_specs.json` + `Maex/memory/ESSA/subtask_specs.json` 草案

2. **`MaexObserver` 实现**
   - 在 `Maex/env/` 下,实现 `env.lightwm_base.BaseEnvObserver` 协议的 4 个方法(vendored 自 LightWM,见 `Maex/env/lightwm_base.py`)
   - `extract_state_patch`:把 Maex 的 obs(scene graph)翻译成 ESSA `subtask_state` 的 patch ops
   - `normalize_action` / `detect_action_verb` / `get_full_action_space`:对接 Maex 的 action 集合

3. **Minimal runner**
   - 在 `Maex/` 内新建一个 minimal entry(例如 `examples/minimal_essa_verify.py`)
   - 装配:`ESSAAgent(env_observer=MaexObserver(), task_specs=..., subtask_specs=...)` + env0 task 0
   - 单任务跑完即算 verify pass

4. **跑通 `land_on_receptacle` family**(verify instance = env0 task 0,健壮性 instance = env0 task 1)
   - **下一个 family 等当前跑通后再识别**。不要预先规划 "task 3 → task 2" 之类的 per-instance 梯度——那违背 task family spec 抽象(见第 4 条决策)。

### 开发约束(高优)

- **不要**给 Maex 引入新的第三方依赖,除非确实必要
- **不要**绕过 schema 设计直接 hack 一个 if-else dispatch —— minimal verify 的目的就是证明 ESSA 的结构化 state + spec 驱动的 subtask 真的能跑,如果绕过这个核心机制就失去验证意义
- **改 vendored 的 ESSA 代码(`agent/essa_agent.py` / `env/lightwm_base.py` / `prompt/essa_prompts.py`)前**,先和学长 / 用户确认 —— 这部分代码来自 LightWM 上游,Maex 的 verify 框架依赖它的语义稳定。改 spec 字段消费规则尤其要谨慎
- 每完成一步先和用户对齐再继续,不要一口气写到底

---

## 进度日志 (Progress Log)

### 2026-05-20

**完成的工作**

- **Git / 仓库设置**
  - 在 GitHub Web 上 fork `BloomChant/Maex` → `ggkiller-air/Maex`
  - 本地 remote 调整:`origin = ggkiller-air/Maex`(自己的开发主战场),`upstream = BloomChant/Maex`(学长仓库,等 verify 跑通后再 PR 回去)
  - 设置 git 全局 identity(`ggkiller-air` / `864975429@qq.com`)
  - `Maex/CLAUDE.md` 已 commit + push 到 `origin/main`(commit `75718f7`)。注意 `智能体网关短期记忆初步对接文档.md` 仍是 untracked,本期未提交

- **调研:LightWM 这边**
  - 通读 `LightWM/agent/ESSAAgent.py` 中 spec 字段的 Python 消费点(已确认 `subtask_status_schema` / `caller_mapping` / `patch_ops_policy.allowed` / `output_para` / `done_when_all` / `sys_output_format` / `operation_space` / `executor_sys_rules` / `base_actions` 等字段都被代码结构性读取,不是单纯 prompt 拼接)
  - 通读 `LightWM/memory/ESSA/task_specs.json` 的 `pick_and_place_simple` entry 全字段 + `subtask_specs.json` 的 `SEARCH_OBJECT` 和 `MOVE_OBJECT_TO_RECEP` entry,作为本期 Maex spec 的格式蓝本
  - 验证 bool 字段配 `done_when_all` 在框架里**显式被支持**(`ESSAAgent.py:820-821` 的 `_is_present`)—— 因此 `agent_above_target` / `landed_on_target` 用 bool 没问题

- **调研:Maex 这边**
  - 通读 `Maex/env/coherent_env.py` 的 `obs2text` 与 `_enumerate_plans`,确认:
    - quadrotor 的合法动作格式:`[takeoff_from] <surface_class>(<id>)` / `[movetowards] <X>(<id>)` / `[land_on] <surface_class>(<id>)`
    - 观察文本里可匹配的关键模式:`Now my state is: <LAND|FLYING>.` / `I am {ON|INSIDE|ABOVE} the <X>(<id>).` / `Now I am in the <room>(<id>). In this room, I can see:`
    - `_enumerate_plans` 已经按当前 quadrotor 状态(LAND/FLYING)+ 门状态(OPEN/OPEN_FOREVER/CLOSED)过滤了合法 `[movetowards]`—— Executor 不需要自己做路径规划,选 legal action list 里任意一个 movetowards-room 就在前进

- **推导:family land_on_receptacle 在 env0 上的 gold path**
  - env0 task 0(降落 high kitchen table=35,kitchen):takeoff → movetowards livingroom → movetowards kitchen → movetowards high kitchen table → land_on,共 5 步,匹配 `gt=5`
  - env0 task 1(降落 dining table=13,livingroom):takeoff → movetowards livingroom → movetowards dining table → land_on,共 4 步,匹配 `gt=4`
  - 两者**走同一份 schema**,只有 `target_receptacle` / `target_receptacle_id` 两个 macro 字段不同 —— 验证 family-level 抽象成立

- **落盘 `Maex/memory/ESSA/`**(目录新建)
  - `task_specs.json`:1 个 family entry `land_on_receptacle`,含 `task_state_schema`(10 字段)、`init_rules`(8 条)、3 步 `base_subtask_sequence`
  - `subtask_specs.json`:3 个 subtask entry:
    - `QUAD_TAKEOFF`(1 env step,LAND → FLYING)
    - `QUAD_FLY_TO_RECEP`(多步,跨房间到目标上方)
    - `QUAD_LAND_ON_RECEP`(1 env step,FLYING+ABOVE → LAND ON target)
  - 通过 JSON parsing + cross-reference 自洽性检查:`base_subtask_sequence` ↔ subtask entries / `output_para` ↔ `task_state.fields` / `caller_mapping.from` ↔ `task_state.fields` / `patch_ops_policy.allowed` ↔ `subtask_status_schema`

**待用户 review 的潜在脆弱点(明天开工前对齐)**

1. `QUAD_TAKEOFF.executor_sys_rules` 让 LLM 自己解析 `memory.takeoff_surface`(字符串 `"on <childroom floor>(3)"`)里的 surface_id —— 可以改成在 MaexObserver 层先解析,把 `agent_on_surface_class` / `agent_on_surface_id` 作为结构化 macro 字段提供
2. `QUAD_FLY_TO_RECEP.executor_sys_rules` 的"目标不在合法动作里 → 任选 `[movetowards] <room>`"策略,仅在 env0 task 0/1 路径**唯一**时安全。后续如果有路径分支(多条门 OPEN)需要 Oracle 协助选路
3. `QUAD_FLY_TO_RECEP.operation_space.update_room` 只匹配了 `"Now I am in the <room>(id). In this room, I can see:"` 这一种换房标志。实跑前建议跑一次真实 `obs2text(obs, agent_idx)` 看看是否所有跨房观察都含这条
4. 没写 `operation_space_full_state` —— `state_update_mode=patch` 默认模式跑得通就够。后期换 `full_state` 模式才需要补

**当前 git 状态(2026-05-20 收工时)**

- `Maex/CLAUDE.md`:已修改(本日志 + 第 4 条决策更新),未 commit
- `Maex/memory/ESSA/task_specs.json` / `subtask_specs.json`:已落盘,untracked
- `Maex/智能体网关短期记忆初步对接文档.md`:历史 untracked,本期未动

**明天的下一步**

CLAUDE.md 第 2 步:**MaexObserver 实现**。在 `Maex/env/coherent/` 下(新建 subdir,或者直接放 `Maex/env/`)写 observer,实现 `LightWM.env.base.BaseEnvObserver` 协议。具体方法清单:
- `extract_state_patch(obs, last_action, ...)` —— 把 Maex obs 翻译成 ESSA `subtask_state` 的 patch ops(StateUpdater 之外的、框架自动注入的部分)
- `normalize_action(action_str)` —— 规范化 LLM 输出,对接 Maex `[verb] <X>(id)` 格式
- `detect_action_verb(action_str)` —— 抽出动词(`takeoff_from` / `movetowards` / `land_on` / ...)
- `get_full_action_space(obs, agent_idx)` —— 调 `coherent_env.get_available_plans(...)` 拿合法动作集
- 此外还有:`macro_fields_to_subtask_core()`(决定哪些 macro 字段每步自动塞进 subtask `core` 让 Executor 看见)、`macro_to_memory_prefill(...)`、`evidence_gate(...)`、`post_process_patch_ops(...)`、`validate_subtask_done(...)` —— 这些都要参考 LightWM 的 `env/alfworld/AlfworldObserver.py` 实现

开工前用户需要先确认上面"待 review 的脆弱点"四条要不要改 spec(尤其是 1、3 两条会影响 Observer 接口设计)。

### 2026-05-22

**Minimal verify PASS** —— land_on_receptacle family 在 env0 跑通 2/2 实例,LightWM ESSA 控制流首次成功驱动 Maex/COHERENT。

- env0 task 0(降落 high kitchen table,gt=5):**5 步 done=True**,与 gold path 完全一致
- env0 task 1(降落 dining table,gt=4):**4 步 done=True**,同一份 spec 自动覆盖
- 模型:本地 vLLM Qwen3-4B-Instruct-2507,2GPU TP,`LightWM/experiment_scripts/start_2gpu_server.sh` 启动

**新增文件**(全部在 `Maex/` 内,LightWM 一字未动)

- `Maex/env/lightwm_maex_observer.py` —— `LightWMMaexObserver(BaseEnvObserver)`,正则解析 `Now my state is: <LAND|FLYING>` / `I am {ON|INSIDE|ABOVE} the <X>(<id>)` / `Now I am in the <room>(<id>)`,输出 macro task_state 的 5 个观察字段 + 双保险算出 `agent_above_target` / `landed_on_target`
- `Maex/agent/lightwm_agent.py` —— `LightWMAgent` 包装 ESSAAgent,内置 `run_episode()` 复刻 ALFWorld smoketest 的 `run_single_task` 逻辑;`__main__` 入口 `python -m Maex.agent.lightwm_agent --env env0 --task 0`  *(2026-05-25 已迁移为 `Maex/run_lightwm.py`,类名 `LightWMRunner`,入口 `python -m run_lightwm`)*
- `Maex/experiment_scripts/run_lightwm_in_maex.sh` —— 设 `DASH_BASE_URL=http://127.0.0.1:<port>/v1` + 自动从 `/v1/models` 探测 model 名 + 设 `PYTHONPATH=AgentGateway:Maex` + 调起 agent  *(2026-05-25 后 PYTHONPATH 只留 `Maex/`;当日晚些时候 .sh 整个删除,逻辑合并进 `run_lightwm.py`)*

**Spec 状态**:`Maex/memory/ESSA/task_specs.json` 和 `subtask_specs.json` 一字未改(2026-05-20 已验收)。一份 family-level spec 自动覆盖 task 0/1 两个实例,验证了 family 抽象成立。

**接入侧实现细节**

- ESSAAgent `_load_specs_with_subdirs` 默认从 `LightWM/memory/ESSA/` 读 spec;`LightWMAgent.__init__` 在实例化后**把 `Maex/memory/ESSA/` 的两份 JSON merge 进 `essa.task_specs` / `essa.subtask_specs`**,这样既不污染 LightWM,也让 `task_type="land_on_receptacle"` 能解析。
- 控制层加了一个**反 backtrack 过滤** `_filter_admissible_no_backtrack`:LLM 进入 livingroom 后,合法动作里既有 `[movetowards] <kitchen>(6)` 又有 `[movetowards] <childroom>(2)`(刚来的房间),首次跑触发 LLM 在两房间间循环。修复方案是**仅在喂给 Executor 的 admissible list 中临时剔除刚离开房间的 movetowards**——spec / env / select_legal_action 全部不变,只是 LLM 视野里少了一个回头选项。spec 验收线没动。

**LightWM 依赖现状(截至 2026-05-22 收工)**

- 强依赖 `LightWM/`(`from LightWM.agent.ESSAAgent`、`from LightWM.env.base`)。当前接入方式 = `PYTHONPATH=AgentGateway:Maex`(在 wrapper script 里设)。
- 实操要求:同时 clone Maex 和 LightWM 到同一父目录(`AgentGateway/`),不能"只 clone Maex"跑起来。要做"自包含"有两条路:把 LightWM 装成 pip 包(需要先解决 `pyproject.toml` 顶级包名 `agent`/`env` 与 Maex 自身冲突)或 vendor 一份 LightWM 进 Maex。本期先保留 PYTHONPATH 方案。

> **2026-05-25 更新**:已走 vendor 路线,Maex 现在自包含。详见下方 2026-05-25 进度条目。

**conda env**

- `lightwm` env(用 `LightWM/experiment_scripts/start_*gpu_server.sh` 默认激活的那个)需要 `backoff`(Maex 现有 agent 的依赖)。已 `pip install backoff` 装上,其它 Maex 第三方依赖`(openai)` 已存在。

**Trace 落点**

- `Maex/logs/lightwm_verify/env0_task<N>_<ts>.json` —— 每步含 StateUpdater raw response / Executor raw response / select_meta / env_result / 观察后的 macro task_state。**HTML 报告生成器待补**(对照 `LightWM/utils/report_builder.py` 和 Maex `gpt5mini-reports/react/*.html` 的风格)。

**下一步候选**(等用户选)

- 接 family B `land_with_payload`(多 agent,涉及 robot_dog / robot_arm 把物体放进 quadrotor basket 后起飞降落),或 family C `put_single_object`(单 agent 切换到 robot_dog,验证 ESSA 在非飞行 agent 上也成立)。具体 family 划分草稿见 user memory `env0-task-family-draft.md`(2026-05-20 未验证)。
- 给当前 verify 流程补一个 HTML 报告生成器,把 JSON trace 渲染成像 `Maex/gpt5mini-reports/react/env0_combined_*.html` 那种可读视图。

### 2026-05-25

**LightWM → Maex vendor 迁移 PASS** —— Maex 切换为自包含,不再依赖 sibling `LightWM/` 目录。`grep -rn 'from LightWM\|import LightWM' Maex/` = **0 匹配**。

**新增 / 移动的文件**

- `Maex/agent/essa_agent.py` —— vendored 自 `LightWM/agent/ESSAAgent.py`(1188 行)。改动:2 处 `from LightWM.*` → `from env.lightwm_base` / `from prompt.essa_prompts`;`_initialize_client` 里 `from LightWM.config import get_settings` 的 try/except 死分支删除(env var fallback 行为等价)。
- `Maex/prompt/essa_prompts.py` —— vendored 自 `LightWM/prompt/ESSA_prompts.py`(442 行)。**注意:文件前 ~100 行的 docstring 和 prompt 文本里仍有大量 ALFWorld 词汇(`receptacle` / `pick_and_place` / `go to` 等),COHERENT 不需要这些 —— 是已知 TODO,后续清理**。
- `Maex/env/lightwm_base.py` —— vendored 自 `LightWM/env/base.py`(209 行,仅 stdlib 依赖)。文件名加 `lightwm_` 前缀以对仗 `lightwm_maex_observer.py`,避免与 Maex 其它 env 模块同名。
- `Maex/run_lightwm.py`(从 `Maex/agent/lightwm_agent.py` 上移 + 改名) —— 类 `LightWMAgent` 同步改名为 `LightWMRunner`。理由:它本质是 runner 不是 agent 算法(自起 episode loop、log 落盘、HTML 报告、`__main__` 入口),职责上对标 `Maex/runner.py` / `Maex/run_suite.py`,与 `agent/` 下的纯算法类不是同质。模块名采用 `run_lightwm` 与 `run_suite` 风格一致。
- `Maex/env/lightwm_maex_observer.py` —— 内部 `from LightWM.env.base` 改为 `from env.lightwm_base`。其余不变。
- `Maex/experiment_scripts/run_lightwm_in_maex.sh` —— **当日晚些时候已删除**,bash 胶水合并进 `run_lightwm.py`:新增 `--port` / `--base-url` / `--api-key` / `--seed` 旗标,`main()` 早期 `os.environ` 设 `DASH_BASE_URL` / `DASH_API_KEY` / `LLM_SEED`。改造目的是对齐 Maex `python -m runner` 风格,不再有 wrapper script。
- `Maex/experiment_scripts/start_{1,2,4}gpu_server.sh` —— 从 `LightWM/experiment_scripts/` 复制进来。`start_1gpu` / `start_4gpu` 原本写死 `cd /mnt/...` 或 `cd LightWM/` 的两行,改成 `cd "$(dirname ...)/.."` 落到 Maex 根。`Maex/` 现在完全不依赖 sibling `LightWM/` 目录。

**目录结构终态**

```
Maex/
├── runner.py                  # Maex 主 runner (react/crms/pefa/drms)
├── run_suite.py               # Maex 批量 runner
├── run_lightwm.py             # LightWM/ESSA 的独立 runner
├── agent/
│   ├── _base.py
│   ├── essa_agent.py          # ★ vendored ESSAAgent 算法
│   ├── react_agent.py
│   ├── pefa_agent.py
│   ├── pefa_wo_history_agent.py
│   ├── crms_agent.py
│   └── drms_agent.py
├── env/
│   ├── lightwm_base.py        # ★ vendored BaseEnvObserver 协议
│   ├── lightwm_maex_observer.py
│   └── coherent_env.py
└── prompt/
    └── essa_prompts.py        # ★ vendored ESSA prompt 模板
```

`agent/` 目录里 6 个 `*_agent.py` 文件清一色都是算法类,跟 Maex 既有惯例对齐。

**没动的东西**

- LightWM 源仓库一字未改 —— vendor 是单向复制,不动上游
- `Maex/memory/ESSA/*.json`(specs)2026-05-20 已就位,本次迁移不动。`run_lightwm` 仍按原方式把 `Maex/memory/ESSA/` 的两份 JSON merge 进 `essa.task_specs` / `essa.subtask_specs`

**验证**

- 静态 import 烟测在 `lightwm` conda env 下全过:`ESSAAgent.__module__ == agent.essa_agent`、`BaseEnvObserver.__module__ == env.lightwm_base`、`LightWMRunner.__module__ == run_lightwm`、`LightWMMaexObserver` MRO 正确继承新的 `BaseEnvObserver`。
- 端到端(连本地 vLLM 跑 env0 task 0)等用户开 vLLM 后跑一次 `python -m run_lightwm --env env0 --task 0` 最终确认。

**Claude 工作目录变更**

- 从今天起,Claude Code 在 `~/Project/AgentGateway/Maex` 启动即可,不再需要 `~/Project/AgentGateway`。详见上方"Claude 启动目录"小节。
