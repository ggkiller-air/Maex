# env2 任务族

## env2 场景 metadata

- **房间:** `grocery store(0)`,floor = `grocery store floor(1)` (LANDABLE)
- **HIGH surface (LANDABLE / arm 可达):** `display table(5)`、`checkout counter(8)`、`display table(42)`、`display bin(2/3/4)` (OPEN_FOREVER)
- **LOW surface:** `pedestal table(6/7)`、`grocery shelf(29)`、`grocery store floor(1)`
- **容器 (open-state):** `cash register(24)` = CLOSED(**所有 task 均不涉及**),`carton(26)` / `display bin(2/3/4)` / `basket(22)` / `shopping basket(30)` / `trash can(23/38)` / `bucket(41)` = 无 open-state
- **Agent:** arm18 ON display table(5)、arm19 ON checkout counter(8)、dog20 ON floor、quad21 ON floor (LAND)
- **Quadrotor 携带的 basket:** `basket(22)` (与 quad21 `WITH` 关系)

## env2 family 列表

### E2-A. `put_objects_on_surface`

- **谓词形态:** 全部 `on_<X>_<Y>`,Y 为 surface (table / shelf / counter / floor);**无 `inside_`* 谓词,无 quad land 占位**
- **agent:** dog 中转 + arm 取放为主(单/双 arm);quad 不参与
- **base_subtask_sequence(雏形):**
  - 若 src 与 dst 同高度可被同一 agent 直达 → `pick(agent, src) → place(agent, dst)`
  - 若跨高度 → `arm_pick → arm_place_to_dog → dog_navigate_to_target → dog_place_on_arm → arm_place_to_dst`(或 `arm→dog→arm` 三段;具体形态待 spec 确认)
- **env2 实例:** **task 0、1、2、9、11、15、17、18、19** (9 个)

### E2-B. `put_objects_into_basket_or_bin`

- **谓词形态:** 至少包含一个 `inside_<X>_<Y>`,Y 为 OPEN_FOREVER 容器 (shopping basket / display bin / trash can / bucket / basket);**无 quad land 占位**;允许同时包含 `on_<X>_<Y>`(把"inside OPEN_FOREVER 容器"与"on surface"视为等价的"放置目标")
- **agent:** dog + arm 协作;quad 不参与
- **base_subtask_sequence(雏形):** 与 E2-A 同形,只是 final 关系从 ON 改成 INSIDE
- **env2 实例:** **task 3、5、7、12、13、14、16** (7 个)

### E2-C. `arm_load_basket_then_quad_land`

- **谓词形态:** `inside_<obj>_<basket>(22)` (装入 quadrotor 的 basket) + `on_<quadrotor>(21)_<某 HIGH surface>`(后者有时 init 已满足,仍按统一形态执行)
- **agent:** arm 装篮 + quad 起飞/降落(env2 单房间,所以无跨房导航,只需"原地起飞 → 飞到目标上方 → 降落")
- **base_subtask_sequence(雏形):** `arm_pick(src) → arm_put_in_basket → quad_takeoff → quad_fly_to_target_surface → quad_land` (统一一份,不分支处理 quad init 是否已就位 —— 即使绕一圈也能达成 goal)
- **env2 实例:** **task 4、6、8、10** (4 个)
- **note:** task 4 (gt=4) 是 env2 最简单的 instance,可作 env2 verify 起点

## env2 逐 task 归属表


| task | gt  | family   | 理由                                                                                     |
| ---- | --- | -------- | -------------------------------------------------------------------------------------- |
| 0    | 8   | **E2-A** | pack of bread + toilet tissue 从 carton → grocery shelf,2 obj × 4 step                  |
| 1    | 8   | **E2-A** | 2 candy 从 grocery shelf → 2 pedestal tables(目的地同 class)                                |
| 2    | 8   | **E2-A** | wallet + paper money 从 floor → pedestal table(7)                                       |
| 3    | 6   | **E2-B** | 3 obj 从 checkout counter → shopping basket(30) (arm19 直达)                              |
| 4    | 4   | **E2-C** | 2 biscuits 从 shopping basket → quad basket;quad 已就位(init OK 占位)                        |
| 5    | 8   | **E2-B** | empty box → trash can(38)、rag → bucket(41) (双目的地容器)                                    |
| 6    | 11  | **E2-C** | 2 candy 从 shelf → quad basket,quad 起飞降落到 display table(42)                             |
| 7    | 10  | **E2-B** | apple 从 display bin(2) → shopping basket(30) (跨高度,需 arm-arm 或 dog 中转)                  |
| 8    | 11  | **E2-C** | OJ + paper money → quad basket,quad 飞 display table                                    |
| 9    | 11  | **E2-A** | biscuits + OJ 从 basket(22) → grocery shelf;**source 是 quadrotor basket,需先就位再取**        |
| 10   | 11  | **E2-C** | candy + pack of bread → quad basket,quad 飞 display table                               |
| 11   | 12  | **E2-A** | chocolate bar 从 checkout counter(HIGH) → pedestal table(LOW),需跨高度                      |
| 12   | 12  | **E2-B** | banana 从 display bin(2) + coin 从 checkout counter → shopping basket                    |
| 13   | 16  | **E2-B** | candy 从 shelf → shopping basket、receipt 从 checkout → display bin(都是容器)                 |
| 14   | 12  | **E2-B** | paper money 从 pedestal table(LOW) → shopping basket(HIGH),跨高度                          |
| 15   | 15  | **E2-A** | apple + OJ 从 display bins(HIGH) → 2 pedestal tables(LOW)                               |
| 16   | 13  | **E2-B** | apple → display bin(2) (container) + pack of bread → pedestal table(6);按"放置目标"等价处理,归 B |
| 17   | 15  | **E2-A** | chocolate bar → grocery shelf、paper money → pedestal table(都是 surface)                 |
| 18   | 15  | **E2-A** | 2 biscuits 从 shopping basket(checkout HIGH) → grocery shelf(LOW)                       |
| 19   | 12  | **E2-A** | OJ 从 display bin(4 HIGH) → grocery shelf(LOW)                                          |


## 当前做法的局限性

1. **spec 强制统一执行路径,部分实例绕路:** 为覆盖跨高度 / quad-需起飞 场景,把 family 内所有实例固化为"arm-dog-arm 三段式中转"(E2-A/B) 或 "takeoff→fly→land"(E2-C),原本可直达 / quad 已就位的实例多走若干冗余步,gt 会被拉长但 goal 仍可达。代表性绕路实例: **task 1、2、3、4**
2. **E2-B 谓词类型合并的提示工程代价:** spec 的"放置目标"字段须兼容 surface / container 两种节点类型,Executor 提示词须明确何时用 `[puton]` 何时用 `[putinto]`。涉及任务: **task 16**
3. `**base_subtask_sequence` 顺序遍历多目标,放弃并行:** env2 中凡 `task_goal` 谓词数 ≥ 2 的 task 均无法利用"多 agent 各自负责一个目标"的并行

