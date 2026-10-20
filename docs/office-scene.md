# The Office tab

The Office tab shows a panda in a small 2D office. It uses Drift's reported activity to choose a pose and place: reading, writing, thinking, browsing or resting. It does not represent extra agents or measure how close a task is to completion.

**Closer look** opens the reported task and its saved report. Saved work is labelled as saved, not presented as an active project. If the backend disconnects, the scene shows the lost connection rather than inventing progress.

You can pause movement. Drift remembers that preference when browser storage is available and respects reduced-motion settings. Hidden or offscreen scenes pause animation. Closing the tab releases the renderer's resources. Inbox remains the first tab.

## Source files

The files are under `frontend/src/`:

- `office/geometry.ts`, `room.ts` and `furniture.ts` draw the room and furniture.
- `office/character.ts`, `layout.ts` and `motion.ts` draw the panda and move it around obstacles.
- `office/renderer.ts` caches static layers and caps device pixel ratio at two.
- `office/OfficeCanvas.tsx` owns the canvas, accessible fallback and snapshots.
- `office/DeskView.tsx` and `work-context.ts` connect the view to actual task data.
- `OfficePanel.tsx` contains the controls. `GameWorld.tsx` keeps the older component interface compatible.

Run `npm test` in `frontend/` for the Office regressions. Check desktop and mobile rendering in a browser as well; a passing build cannot show you whether a paw misses the keyboard or a button is clipped.
