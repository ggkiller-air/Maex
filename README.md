# Maex — Multi-Agent Execution Framework

A research framework for multi-agent collaborative task execution. Agents with heterogeneous capabilities (aerial, mobile, fixed-arm) coordinate to complete long-horizon manipulation tasks in indoor environments.

Currently validated on a symbolic simulation built around the [COHERENT](https://github.com/tobran/COHERENT) task suite, with the architecture designed to extend to other environments and execution frameworks.

## Agents

| Class | Type | Capabilities |
|-------|------|-------------|
| `quadrotor` | Aerial | Fly between rooms, transport objects at height |
| `robot_dog` | Mobile manipulator | Navigate rooms, grab / place objects |
| `robot_arm` | Fixed manipulator | High-precision grab / place at a fixed table |

## Methods

| Method | Description |
|--------|-------------|
| `react` | Two-call per step: T1 oracle assigns coarse subgoal → T2 agent picks action (Thought + Action) |
| `pefa` | Oracle + feasibility check + action + judge |
| `crms` | Centralized oracle with per-agent instruction extraction |
| `drms` | Decentralized multi-round negotiation per agent |

## Environments

Five symbolic indoor environments, each with ~20 tasks:

| Env | Scene | Paper tasks |
|-----|-------|-------------|
| env0 | Bedroom | 2 4 9 10 11 15 16 20 |
| env1 | Living room | 1 3 7 8 10 11 16 20 |
| env2 | Grocery store | 3 5 6 7 10 11 16 17 |
| env3 | Restaurant | 2 4 6 7 10 16 17 19 |
| env4 | Lower living room | 0 1 7 10 12 17 18 19 |

## Setup

```bash
pip install openai backoff
export OPENAI_API_KEY=<your_key>
# or set OPENAI_BASE_URL for a custom proxy
```

## Running

**Single task:**
```bash
python -m maex.runner --method react --env env0 --tasks 2 --lm_id gpt-4o-mini
```

**Full paper suite (40 tasks, 5 envs):**
```bash
python -m maex.run_suite --methods react --lm_id gpt-4o-mini
```

**Specific envs / tasks:**
```bash
python -m maex.run_suite --methods react --envs env0 env1 --lm_id gpt-4o-mini
python -m maex.run_suite --methods react --envs env0 --tasks-env0 2 4 9 --lm_id gpt-4o-mini
```

**Parallel runs:**
```bash
python -m maex.run_suite --methods react --parallel 4 --lm_id gpt-4o-mini
```

**Key options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--lm_id` | `gpt-5-mini` | Model ID |
| `--max_steps` | 30 | Max steps per task |
| `--history_window` | 0 (full) | Dialogue history window (0 = unlimited) |
| `--reasoning_effort` | `low` | For reasoning models: `minimal/low/medium/high` |

## Output

```
maex/logs/json/<method>/<env>/task_<id>/   # structured JSON logs
maex/reports/<method>/                      # HTML visualization reports
```

Each run generates an interactive HTML report with per-step LLM call details, token/cost stats, and a combined multi-task view.

## Project Structure

```
maex/
├── agent/          # ReAct, PEFA, CRMS, DRMS implementations
├── env/            # Symbolic environment + task JSON files (env0–env4)
├── prompt/         # LLM prompt templates
├── utils/          # Logging, reporting, pricing
├── runner.py       # Single-task entry point
└── run_suite.py    # Batch runner with CSV summary
```
