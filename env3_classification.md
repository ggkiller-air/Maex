# env3 任务族

## env3 场景 metadata

- **房间:** `restaurant(0)`,floor = `restaurant floor(1)` (LANDABLE)
- **HIGH surface (LANDABLE / arm 可达):** `dining table(2/3)`、`bar counter(10/11)`
- **LOW surface:** `coffee table(4/5)`、`sofa(6/7)`、`ottoman(8/9)`、`restaurant floor(1)`
- **容器 (open-state):** `coffee maker(13)` = CLOSED、`cash register(17)` = CLOSED;另部分 task 在自身 init_graph 中引入 `toaster oven`(task 12) / `microwave`(task 15) = CLOSED。`basket(22)` / `trash can(24/25)` / `plastic bag`(task 17) = 无 open-state
- **Agent:** arm18 ON bar counter(10)、arm19 ON bar counter(11)、dog20 ON floor、quad21 ON floor (LAND)
- **Quadrotor 携带的 basket:** `basket(22)` (与 quad21 `WITH` 关系)

## env3 family 列表

### E3-A. `put_objects_on_surface`

- **谓词形态:** 全部 `on_<X>_<Y>`,Y 为 surface (table / bar counter / sofa / ottoman / floor);**无 `inside_*` 谓词,无 quad land 占位**
- **agent:** dog 中转 + arm 取放为主(单/双 arm);quad 不参与
- **base_subtask_sequence(雏形):**
  - 若 src 与 dst 同高度可被同一 agent 直达 → `pick(agent, src) → place(agent, dst)`
  - 若跨高度 → `arm_pick → arm_place_to_dog → dog_navigate_to_target → dog_place_on_arm → arm_place_to_dst`(或 `arm→dog→arm` 三段;具体形态待 spec 确认)
  - 若 src 在 CLOSED 容器内(如 task 12 source = toaster oven) → 前置 `arm_open(container)` 子序列
- **env3 实例:** **task 1、3、4、5、8、12、16、18** (8 个)

### E3-B. `put_objects_into_basket_or_bin`

- **谓词形态:** 至少包含一个 `inside_<X>_<Y>`,Y 为 容器 (trash can / plastic bag / cash register);**无 quad land 占位**;允许同时包含 `on_<X>_<Y>`(把"inside 容器"与"on surface"视为等价的"放置目标")
- **agent:** dog + arm 协作;quad 不参与
- **base_subtask_sequence(雏形):** 与 E3-A 同形,只是 final 关系从 ON 改成 INSIDE;若 dst 是 CLOSED 容器(如 task 14 dst = cash register)→ 前置 `arm_open(container)` 子序列
- **env3 实例:** **task 0、14、17** (3 个)

### E3-C. `arm_load_basket_then_quad_land`

- **谓词形态:** `inside_<obj>_<basket>(22)` (装入 quadrotor 的 basket) + `on_<quadrotor>(21)_<某 HIGH surface>`(后者有时 init 已满足,仍按统一形态执行);允许额外包含其它 `inside_<X>_<非 basket 容器>` 谓词作为"前置垃圾/收纳"子目标(task 13)
- **agent:** arm 装篮 + quad 起飞/降落(env3 单房间,所以无跨房导航,只需"原地起飞 → 飞到目标上方 → 降落");跨高度取物时 dog 中转
- **base_subtask_sequence(雏形):** `[可选前置 subtask] → arm_pick(src) → arm_put_in_basket → quad_takeoff → quad_fly_to_target_surface → quad_land` (统一一份,不分支处理 quad init 是否已就位);若 src 在 CLOSED 容器内(如 task 15 source = microwave)→ 前置 `arm_open(container)`
- **env3 实例:** **task 2、6、7、9、10、11、13、15、19** (9 个)
- **note:** task 2 (gt=4) 是 env3 最简单的 instance,可作 env3 verify 起点

## env3 逐 task 归属表


| task | gt  | family   | 理由                                                                                     |
| ---- | --- | -------- | -------------------------------------------------------------------------------------- |
| 0    | 8   | **E3-B** | 2 paper cups 从 coffee tables → trash can(25),全 LOW dog 操作                              |
| 1    | 4   | **E3-A** | beer glass + beer bottle 从 bar counter(11) → tray (init OK on bar counter(11));arm19 直达 |
| 2    | 4   | **E3-C** | milk + bread → quad basket;quad 已就位 on bar counter(11) (init OK 占位)                    |
| 3    | 8   | **E3-A** | milk + bread 从 basket(22 floor) → coffee table(4 LOW);dog 操作                            |
| 4    | 7   | **E3-A** | swap coffee cup / milk between coffee table(4)(5);dog 操作                                 |
| 5    | 10  | **E3-A** | coffee cup 从 bar counter(10) → tray on bar counter(11);跨 arm 传递                        |
| 6    | 10  | **E3-C** | beer glass + bottle → quad basket,quad 飞 dining table(2)                              |
| 7    | 11  | **E3-C** | napkin(coffee table) + coffee cup(sofa) → quad basket,quad 飞 dining table(2)            |
| 8    | 11  | **E3-A** | bread + syrup 从 basket(22) → coffee table(5);dog                                       |
| 9    | 10  | **E3-C** | coffee cup → quad basket;quad 已就位 on tableware recycling table (init OK 占位)              |
| 10   | 10  | **E3-C** | hamburger 从 coffee table(4) → quad basket,quad 飞 dining table(3)                        |
| 11   | 8   | **E3-C** | receipt 从 bar counter(11) → quad basket (arm19 直放),quad 飞 dining table(3)                |
| 12   | 13  | **E3-A** | bread 从 `toaster oven(CLOSED)` → coffee table(4);**source 需 open**                       |
| 13   | 14  | **E3-C** | 复合:先把 paper cup 扔进 trash can(24),然后 beer glass+bottle 装篮 + quad 飞 dining table(2)   |
| 14   | 10  | **E3-B** | cash 从 ottoman → `cash register(17, CLOSED)`;**dst 需 open**                              |
| 15   | 13  | **E3-C** | coffee cup 从 `microwave(CLOSED)` + napkin 从 ottoman → quad basket,quad 飞 dining table(2);**source 含 CLOSED 容器** |
| 16   | 12  | **E3-A** | paper sheet 从 coffee table(4 LOW) → bar counter(10 HIGH);跨高度                            |
| 17   | 12  | **E3-B** | cookie 从 coffee table(5) → plastic bag(init OK on bar counter(11));plastic bag 非 CLOSED |
| 18   | 12  | **E3-A** | juice 从 bar counter(10 HIGH) → coffee table(5 LOW);跨高度                                  |
| 19   | 12  | **E3-C** | hot dog(bar counter 10) + tray(coffee table 5) → quad basket,quad 飞 dining table(2)      |


## 当前做法的局限性

1. **spec 强制统一执行路径,部分实例绕路:** 为覆盖跨高度 / quad-需起飞 场景,把 family 内所有实例固化为"arm-dog-arm 三段式中转"(E3-A/B) 或 "takeoff→fly→land"(E3-C),原本可直达 / quad 已就位的实例多走若干冗余步,gt 会被拉长但 goal 仍可达。代表性绕路实例: **task 1、2、9、11**
2. **CLOSED 容器源/目的引入固化 open 子序列:** env3 引入 `toaster oven` / `microwave` / `cash register` 等 CLOSED 容器作为 source / dst,spec 必须在 base_subtask_sequence 内固化"`arm_open(container)` → ... → 可选 `arm_close(container)`",同 family 内同时存在"含 CLOSED 端点"与"不含"两类实例,均走同一份(冗余)spec。涉及任务: **task 12、14、15**
3. **`base_subtask_sequence` 顺序遍历多目标,放弃并行:** env3 中凡 `task_goal` 谓词数 ≥ 2 的 task 均无法利用"多 agent 各自负责一个目标"的并行;**task 13 的"先 trash 后 quad-land"复合形态被强行塞进 E3-C 的统一 spec,使 C 的 base_subtask_sequence 必须预留"可选前置 subtask"位**
