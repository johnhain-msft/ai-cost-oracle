# Demo — a real session, start to finish

Everything below is the unedited output of a real run on a machine with
existing Claude Code and GitHub Copilot CLI history. The full raw capture is in
[`transcript.txt`](transcript.txt).

## 1. The training round

The oracle builds its baseline corpus from local session history — exact token
usage from Claude Code transcripts, and per-request AIC (AI credit) spend from
Copilot's session store.

```console
$ cost-oracle train
Training round complete -> /Users/johnhain/.cost-oracle/corpus.json
  claude     1,463 requests across    14 sessions | models: claude-fable-5
  copilot   72,604 requests across 10,331 sessions | models: claude-haiku-4-5, claude-opus-4-7,
            claude-opus-4-8, claude-opus-5, claude-sonnet-4-6, claude-sonnet-5, gemini-3-1-pro-preview,
            gpt-5-4, gpt-5-4-mini, gpt-5-5, gpt-5-6-luna, gpt-5-6-sol, gpt-5-mini, gpt-6-1-sol,
            gpt-6-luna, mai-code-1-1-flash
```

## 2. A Claude estimate (token-based, USD) with a budget check

```console
$ cost-oracle estimate --provider claude --model claude-opus-5 \
    --task "Add OAuth login to a Next.js app" --complexity moderate --budget 15
Estimate [f73ee3a7]  claude / claude-opus-5
  task:       Add OAuth login to a Next.js app
  complexity: moderate (~72 requests)
  expected:   $9.70
  range:      $5.32 - $16.29
  basis:      tokens/request from all-model baseline, priced at claude-opus-5 rates
  feedback:   cost-oracle feedback f73ee3a7 --actual <cost>
  budget:     $15.00 -> FITS (expected $9.70)
```

## 3. A Copilot estimate (AIC-based)

```console
$ cost-oracle estimate --provider copilot --model claude-opus-5 \
    --task "Refactor the payment service and add tests" --complexity complex
Estimate [b8c0ce5a]  copilot / claude-opus-5
  task:       Refactor the payment service and add tests
  complexity: complex (~70 requests)
  expected:   847.69 AIC
  range:      637.70 AIC - 1,186.27 AIC
  basis:      AIC/request from claude-opus-5 history
  feedback:   cost-oracle feedback b8c0ce5a --actual <cost>
```

## 4. Feedback — the oracle learns from its misses

The real task ended up costing $11.42. Reporting that recalibrates future
estimates (an exponentially-weighted blend, so one outlier can't whipsaw it).

```console
$ cost-oracle feedback f73ee3a7 --actual 11.42
Feedback recorded for [f73ee3a7] (claude)
  estimated: $9.70
  actual:    $11.42
  error:     15.0% under-estimated
  calibration: x1.000 -> x1.050 (1 feedback samples)

$ cost-oracle status
Corpus trained at 2026-10-24T13:45:26+00:00
  claude: 1,463 requests, 14 sessions
  copilot: 72,604 requests, 10,331 sessions
  claude calibration x1.050 | MAPE 15.1% over 1 samples
```

## Inside Claude Code

With the skill and agent installed, the same flow is conversational:

> **You:** How much will it cost to add OAuth login to my Next.js app? Keep the
> estimate itself under $0.05 and use Haiku for it.
>
> **Claude:** _(delegates to the `cost-oracle` agent with a `claude-haiku-4-5`
> model override, in budget mode — status check + one estimate call only)_
> Expected **$9.70** (range $5.32–$16.29) on claude-opus-5, moderate tier.
> Estimate id `f73ee3a7` — tell me the actual cost afterward and I'll
> recalibrate.
