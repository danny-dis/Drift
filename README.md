# Drift

[![CI](https://github.com/danny-dis/Drift/actions/workflows/ci.yml/badge.svg)](https://github.com/danny-dis/Drift/actions/workflows/ci.yml)

Drift is a notebook on your computer for unfinished thoughts, research and project notes. Save what you mean, even if it is messy. Optional AI can suggest a summary, questions or connections to your projects. It keeps your original words.

Version [0.2.3](https://github.com/danny-dis/Drift/releases/tag/v0.2.3) adds editable thoughts, ideas and projects, a directly accessible mind map and wiki pages you can ask AI to create. Read [what changed](docs/releases/0.2.3.md).

## Install and open it

Install Python 3.12 or 3.13, then run:

```bash
python -m pip install --upgrade "https://github.com/danny-dis/Drift/releases/download/v0.2.3/drift-0.2.3-py3-none-any.whl"
python -m drift.main --box ./drift_box --name Drift
```

Open **http://localhost:47116**. Keep the terminal open; press Ctrl+C to stop Drift. The release includes the dashboard, so you do not need Node.js to use it.

`./drift_box` holds your saved work. Keep that folder when you upgrade, and pass the same `--box` path next time. To use another port, add `--port 47117` and open that port in your browser.

## Use it each day

1. Open **Thoughts**, write a thought and save it. Ctrl/Cmd+Enter also works. You do not need to choose a category.
2. **Saved** means Drift has kept your original. It does not mean AI has finished processing it.
3. Open the thought later to read the original and any saved suggestions. Review suggestions before acting on them.

You can save and search without an AI connection. Drafts normally survive a reload, and retrying a failed save does not create another copy. If browser storage is blocked or full, keep the page open until the thought is saved. [How saving and recovery work](docs/thought-capture.md).

If AI work stops, open **Needs approval** and read the blocker. Fix the connection or settings before approving the same task to retry. Drift keeps incomplete replies for review; it does not label them finished or create replacement tasks to dodge a limit.

### Find the other pages

Thoughts, ideas and projects have their own lists and detail pages. You can add, view, edit, archive and restore each one. Editing a thought keeps its original wording. Archive hides work and pauses unfinished processing; restore brings it back without approving that processing.

You can bookmark pages and use browser Back and Forward. On a phone, use the page selector in place of the tab row.

- **Office** shows a panda acting out the task Drift reports. You can pause movement. The scene is an illustration, not proof that extra workers are running.
- **Projects** keeps related ideas together. You can link a repository, review its briefing and choose when to publish Drift's section in `drift.md`. Drift does not silently modify source code.
- **Ideas** lists the ideas separately so they are not buried under another page.
- **Mind map** shows stored relationships. Open a node to read its thought, idea or project, or use the equivalent list.
- **Wiki** saves source-linked AI pages after you explicitly request generation. Choose a project by name, review the sources and check any stale or incomplete-output warning. The [Wiki guide](docs/wiki.md) explains usage and recovery. A project briefing is not a wiki page.
- **Research** saves questions, sources and reports. Citations show where an answer came from; they do not prove it is correct.
- **Activity & budget** shows tasks, call allowances and usage estimates. Estimates are not billing receipts.
- **Needs approval** lists work waiting for your review. Approval lets that task continue; it does not start a coding agent.
- **Workspace** shows the connection and runtime details.

## Connect optional AI

Open **Getting started** and choose **Check AI connection**. That explicit check uses one model call. Merely opening Drift or the guide does not call a model.

The defaults expect a separately running DMR-X gateway at `http://127.0.0.1:47113/v1`, using `auto-free`. Drift does not install or start that gateway. Source settings are in `config.yaml`; installed releases include their own defaults. `DRIFT_PROVIDER`, `DRIFT_BASE_URL` and `DRIFT_MODEL` override them.

Free-only mode refuses ordinary paid-provider routes and has no silent paid fallback. Keep provider credentials in environment variables, never in committed files or the dashboard's token field.

Your saved box is local. **AI processing may send thought content to a remote provider.** Credential filtering cannot remove every kind of private information, so only submit content you are willing to share with that provider.

## Keep your work safe

Back up the box before an upgrade. Do not run two services against it. If a checkpoint is corrupt or unreadable, restore a known-good backup or repair it; do not delete it to make Drift start.

Keep Drift on your own machine. It binds to `127.0.0.1` by default. Shell execution is off, and enabling it is not an operating-system sandbox. If you configured `DRIFT_API_TOKEN`, enter that Drift token in **Connection settings**, not a provider secret. The browser keeps it for the session when storage is available.

Read [safety and limits](docs/safety.md) for authentication, repository access, usage accounting and recovery details. To restart failed workers automatically in a source installation, use the optional [local supervisor](docs/local-runtime.md).

## What has been tested?

Local Windows runs passed 874 Python tests on both Python 3.12 and 3.13, with one symlink case skipped on that host. All 19 frontend checks passed. Browser tests covered ten pages at five screen sizes, including editing, archive/restore and recovery after errors.

Real Mercury 3 tests generated a wiki page with saved sources and processed a thought into an advisory answer. Both results survived restart; reading them and retrying the saved capture did not spend another model call. The package also installed in a clean environment. The release workflow checks Windows and Linux on both supported Python versions before publishing; the CI badge above links to the recorded runs.

These checks do not prove that AI answers are correct or that Drift can run unattended for weeks. Review reports, keep backups and watch disk space. Drift reports degraded health when disk usage reaches 90%.

## Run from source

Use Python 3.12 or 3.13, Node.js 22.23.3 or newer, and npm. CI uses Node 22.

```bash
python -m pip install -e '.[test]'
cd frontend && npm ci && npm test && npm run build && cd ..
python -m pytest tests -q -p no:cacheprovider
python -m drift.main --box ./drift_box --name Drift
```

The build selects production React even if your shell sets `NODE_ENV=development`. For hot reload, run `cd frontend && npm run dev`; Vite uses port 5173 and proxies to 47116. Set `DRIFT_ALLOWED_ORIGINS=http://localhost:5173` if needed. An allowed browser origin is not authentication.
