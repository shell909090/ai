CONFIG ?= $(HOME)/.config/little_agent/config.yaml

.PHONY: all \
        compress-baseline compress-quality compress \
        tools-swap tools-select tools-capability tools \
        pressure-turns pressure-tools pressure \
        system-compliance fence-baseline fence-inject fence system

# ── Chapter 2: Compress ───────────────────────────────────────────────────────
2.0-compress_baseline.jsonl: 2.0-compress_gen_baseline.py
	uv run python 2.0-compress_gen_baseline.py --config $(CONFIG) > $@

compress-baseline: 2.0-compress_baseline.jsonl

compress-quality: 2.1-compress_quality.py 2.0-compress_baseline.jsonl
	uv run python 2.1-compress_quality.py --config $(CONFIG) $(ARGS)

compress: compress-baseline compress-quality

# ── Chapter 3: Tools ──────────────────────────────────────────────────────────
# 3.1: swap — name/description/history signal priority (8 groups × 6 calls)
tools-swap:
	PYTHONUNBUFFERED=1 uv run python 3.1-tools_swap.py --config $(CONFIG) $(ARGS)

# 3.2: select — capability overlap preference (4 scenarios × 3 conditions × 5 calls)
tools-select:
	PYTHONUNBUFFERED=1 uv run python 3.2-tools_select.py --config $(CONFIG) $(ARGS)

# 3.3: capability — progressive ban loop (9 problems × up to 8 rounds)
# Exit code 1 = unknown method encountered; add keyword to KEYWORD_BANS and re-run.
# To run a single problem: make tools-capability ARGS="--problems 2.1"
tools-capability:
	PYTHONUNBUFFERED=1 uv run python 3.3-tools_capability.py --config $(CONFIG) $(ARGS)

tools: tools-swap tools-select tools-capability

# ── Chapter 4: Pressure ───────────────────────────────────────────────────────
# 4.1: continuous conversation until crash (no turn limit)
# Mode A: short questions. Mode B: long content.
# Example: make pressure-turns ARGS="--mode B"
pressure-turns:
	PYTHONUNBUFFERED=1 uv run python 4.1-pressure_turns.py --config $(CONFIG) $(ARGS)

# 4.3: tool call pressure (fresh session per turn, read + bash tools)
# Variant small (~10 tok/call) or large (~80 tok/call).
# Example: make pressure-tools ARGS="--variant large"
pressure-tools:
	PYTHONUNBUFFERED=1 uv run python 4.3-pressure_tools.py --config $(CONFIG) $(ARGS)

pressure: pressure-turns pressure-tools

# ── Chapter 5: System prompt ──────────────────────────────────────────────────
# 5.1: compliance — S0–S7 scenarios
# To run a single scenario: make system-compliance ARGS="--scenario S4"
system-compliance:
	PYTHONUNBUFFERED=1 uv run python 5.1-system_compliance.py --config $(CONFIG) $(ARGS)

# 5.2: fence — F0 baseline + F1 injection (20 variants × 5 runs each)
fence-baseline:
	PYTHONUNBUFFERED=1 uv run python 5.2-system_fence.py --config $(CONFIG) --variant A $(ARGS)

fence-inject:
	PYTHONUNBUFFERED=1 uv run python 5.2-system_fence.py --config $(CONFIG) --variant B $(ARGS)

fence: fence-baseline fence-inject

fence-f2:
	PYTHONUNBUFFERED=1 uv run python 5.2-system_fence.py --config $(CONFIG) --variant F2 $(ARGS)

fence-f3:
	PYTHONUNBUFFERED=1 uv run python 5.2-system_fence.py --config $(CONFIG) --variant F3 $(ARGS)

system: system-compliance fence fence-f2 fence-f3

# ── Run everything ────────────────────────────────────────────────────────────
all: compress tools pressure system
