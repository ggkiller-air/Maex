# 检查当前容器是否占用显卡资源

```bash
pgrep -af vllm 
```
---

# LightWM → Maex 运行手册


## 1. 启动本地 vLLM

```bash
cd ~/Project/AgentGateway/Maex
conda activate lightwm

export CUDA_VISIBLE_DEVICES=1,2
# 单卡
bash experiment_scripts/start_1gpu_server.sh
# 或两卡
bash experiment_scripts/start_2gpu_server.sh
# 或四卡
bash experiment_scripts/start_4gpu_server.sh
```

挑一个适合你机器的脚本。它会监听 `--port`(默认 8000),并在 HTTP 接口 `http://127.0.0.1:<port>/v1/models` 上暴露当前加载的模型名。要换模型 / 调 `TP_SIZE` / `MAX_MODEL_LEN`,直接编辑脚本顶部变量。

---

## 2. 跑 verify

vLLM 起来后,**另开一个终端**(第 1 步那个要留着挂着 vLLM):

```bash
cd ~/Project/AgentGateway/Maex
conda activate lightwm

python -m run_lightwm --env env0 --task 0
```

默认 `--port 8000` 自动从 `/v1/models` 探测模型名,无需手动 export 任何 env。常用旗标:

| 旗标 | 默认 | 说明 |
|---|---|---|
| `--env` | `env0` | `env0`..`env4` |
| `--task` | `0` | 该 env JSON 中的 task index |
| `--task-type` | `land_on_receptacle` | 必须在 `Maex/memory/ESSA/task_specs.json` 中有对应 entry |
| `--port` | `8000` | 本地 vLLM 端口 |
| `--base-url` | (空) | 覆盖端点,默认由 `--port` 构造为 `http://127.0.0.1:<port>/v1` |
| `--model-name` | (空) | 空则自动探测 |
| `--api-key` | `local` | 透传给 LLM client |
| `--seed` | `1` | LLM 采样种子(设 `LLM_SEED`) |
| `--action-space-mode` | `base` | `base` / `full` |
| `--state-update-mode` | `patch` | `patch` / `full_state` |
| `--max-steps` | `20` | episode 步数上限 |
| `--max-subtask-steps` | `15` | 单个 subtask 步数上限 |

---

## 3. 看输出

- **stdout**:每步打印 StateUpdater / Executor 的 raw response、env 反馈、当前 macro task_state。
- **JSON trace**:`Maex/logs/lightwm_verify/<env>_task<N>_<timestamp>.json`,每步一条完整记录(LLM raw / parsed / env result / state after)。
- **HTML 报告**:`Maex/logs/lightwm_verify/<env>_task<N>_<timestamp>.html`,JSON trace 的渲染视图(当前为初版,后续会对照 `Maex/reports/` 风格调整)。

<!-- 1. 当前HTML格式、内容都还需调整
2. run_lightwm.py脚本对于多任务跑需要兼容，步数`--max-steps` `--max-subtask-steps`限制后续需要动态调整 -->



