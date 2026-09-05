# Drift

A minimal, self-contained AI agent that lives in a single folder. Like a tamagotchi or pet hermit crab — it thinks continuously, explores files you give it, does web research, and builds up knowledge over time.

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
- **Single folder world.** The crab can only touch files inside its `{name}_box/`.
- **Continuous thinking.** The crab thinks on a steady pulse, not just in response to input.
- **Organic memory.** Dreams consolidate thoughts into lasting memories that shape personality over time.

## Code Style

- Python: simple, readable, minimal dependencies. No over-engineering.
- TypeScript: functional React components, hooks for state.
- Keep files short and focused. Each file does one thing.
