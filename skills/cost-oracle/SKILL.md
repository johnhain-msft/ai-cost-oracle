---
name: cost-oracle
description: Predict the cost of an AI request before you spend it. Use when the user asks how much a task will cost, wants a cost estimate for Claude (USD, token-based) or GitHub Copilot (AIC, credit-based), wants to train/retrain the cost baseline from their session history, wants a budget check, or wants to report how accurate a previous estimate was. Triggers - "how much will this cost", "estimate the cost", "cost oracle", "train the cost model", "that estimate was off".
---

# Cost Oracle

Predict what an AI task will cost before running it. Claude estimates are
token-based (priced in USD at published API rates); Copilot estimates are
AIC-based (AI credits, read from Copilot's own session records). Baselines come
from a training round over the user's local session history, and a feedback
loop recalibrates estimates over time. Everything runs locally.

The CLI lives in this skill's own directory: run every command as

    python3 "<this skill's base directory>/scripts/cli.py" <subcommand> ...

using the base directory shown at the top of this skill when it loaded.

## Subcommands

| User intent                  | Command                                                                                                                     |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Train / retrain the baseline | `cli.py train`                                                                                                              |
| Estimate a task              | `cli.py estimate --provider <claude\|copilot> --model <id> --task "<desc>" --complexity <tier> [--requests N] [--budget X]` |
| Report an actual cost        | `cli.py feedback <estimate-id> --actual <cost>`                                                                             |
| Show corpus + accuracy       | `cli.py status`                                                                                                             |
| List model pricing           | `cli.py models`                                                                                                             |

Complexity tiers: `quick`, `simple`, `moderate` (default), `complex`, `epic`.
They anchor to percentiles of the user's own observed sessions.

## Flow

1. **First use / stale corpus:** run `status`; if there is no corpus, run
   `train` and summarize what it found (requests, sessions, models) before
   estimating. Training is read-only over `~/.claude/projects` and
   `~/.copilot/session-store.db`.
2. **Estimating:** pick the provider and model from the user's request. Pick
   the complexity tier from the task description and say which tier you chose.
   If the user gives a budget for the task itself, pass `--budget` — the CLI
   prints FITS or EXCEEDS and exits 2 on EXCEEDS.
3. **Always show the estimate id** and the ready-to-paste feedback command —
   feedback is how the oracle improves.
4. **Feedback:** run the `feedback` subcommand with the id and actual cost;
   report the error percentage and the calibration change.

## Budget and model for the estimation itself

The user may constrain how much may be spent producing the estimate and which
model does the work, e.g. "estimate this, but spend at most $0.05 using haiku".

- **Model constraint:** delegate the estimation to the `cost-oracle` agent with
  an explicit `model` override matching the user's choice (this is a
  deliberate, user-directed override). If the agent is not installed, do the
  CLI calls directly and note the model constraint applies to the session model.
- **Budget constraint:** instruct the agent (or yourself) to run in budget
  mode: `status` + one `estimate` call, no exploration. Report that the
  estimate was produced within the stated budget.

## Rules

- Numbers come from the CLI only — never price a request from memory.
- Relay CLI errors and their suggested fixes verbatim; do not invent numbers.
- All data stays local; never transmit session history.
