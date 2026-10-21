# Wiki pages

Open **Wiki** from the page navigation to create a saved answer from your thoughts, ideas and project notes. You choose when to request generation. A project's `drift.md` briefing is still a different document.

## Create a page

1. Open **Wiki**, then **Generate wiki page**.
2. Enter a title. Choose a project by name, or leave **All active saved work** selected.
3. Read the privacy and usage warning. **Confirm and queue generation** creates the task; opening the form does not.
4. Open the saved page to check its status. **Refresh saved page** reads the existing attempt without queueing another one.

Your configured AI provider must be reachable, and the request must fit your call allowance and context limit. Free-only mode and the normal usage checks still apply. A request can remain queued or become blocked; a successful queue response does not mean the answer is finished.

The release tests generated a real page with Mercury 3, reopened it through a restarted worker and followed its source links in the browser. Refreshing and reloading used no extra model calls. That test does not change your provider settings or make generated statements verified facts.

## Read the result

The source links open the saved thought, idea or project. Read them before trusting the answer. Drift labels generated text unverified and displays it as text rather than executing embedded HTML.

A page warns you when its sources have changed. It also reports sources omitted from the context and excerpts shortened to fit. The answer may therefore cover only part of your saved work. The full original stays in Drift.

An unfinished answer appears under **Read unfinished output**. It is not a completed wiki page. Generation errors remain visible, with a link to the blocked task when one exists.

## Recover a blocked or interrupted request

Open **Needs approval** and read the blocker before approving a saved task. Fix the provider connection or allowance first. Restoring an archived source does not approve its old tasks.

Approval covers the source versions you reviewed. Editing a held, restored source also requires another approval; an older approval cannot silently cover the changed record. A new, explicitly confirmed wiki request can use the restored sources without resuming their older tasks.

An original thought and its generated ideas share processing lineage. Archiving an idea or a related project also excludes that original and its linked projections from wiki context, even if you can still read the original. Independent saved work remains eligible.

If Drift stopped while saving the queue, reopening the page links its existing task when possible. It does not create a replacement task or call a model just because you read the page. If no task was saved, the page reports the interrupted handoff and keeps its sources; return to Wiki and explicitly request a new page.

Back up the box before repairing unreadable checkpoints. Deleting a checkpoint to clear a warning can lose the work or its accounting history.

See [saving and recovery](thought-capture.md) and [safety and limits](safety.md).
