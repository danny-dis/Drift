# Drift

A minimal, self-contained AI agent that lives in a single folder. Like a tamagotchi or pet cat — it thinks continuously, explores files you give it, does web research, and builds up knowledge over time.

## Project Structure

- `drift/` — Python backend (FastAPI + thinking loop)
- `frontend/` — React (Vite + TypeScript) web UI

## Running

```bash
# Backend
pip install -e .
python drift/main.py

# Frontend (dev)
cd frontend && npm install && npm run dev
```

## Design Principles

- **Radically simple code.** Someone who barely codes should be able to follow every file.
- **Single folder world.** The cat can only touch files inside its `{name}_box/`.
- **Continuous thinking.** The cat thinks on a steady pulse, not just in response to input.
- **Organic memory.** Dreams consolidate thoughts into lasting memories that shape personality over time.

## Code Style

- Python: simple, readable, minimal dependencies. No over-engineering.
- TypeScript: functional React components, hooks for state.
- Keep files short and focused. Each file does one thing.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **drift** (897 symbols, 1549 relationships, 36 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/drift/context` | Codebase overview, check index freshness |
| `gitnexus://repo/drift/clusters` | All functional areas |
| `gitnexus://repo/drift/processes` | All execution flows |
| `gitnexus://repo/drift/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
