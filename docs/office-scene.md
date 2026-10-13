# Drift office scene

The old 384-pixel bitmap bedroom is replaced by original procedural 2D isometric office artwork. It is not a photorealistic 3D render.

- `office/geometry.ts`: projection and reusable material primitives.
- `office/room.ts`: timber floor, cutaway walls, window, curtains, daylight and woven rug.
- `office/furniture.ts`: workstation, monitor, individual keyboard keys, task lamp, chair, shelving, sofa, books and plants.
- `office/character.ts`: softly shaded crab and state-aware expression.
- `office/renderer.ts`: cached static layers, furniture/character depth ordering, high-DPI output, responsive sizing and visibility/motion controls.
- `office/OfficeCanvas.tsx`: reusable React lifetime, accessible fallback and snapshot boundary.
- `OfficePanel.tsx`: optional dashboard office with a truthful backend-status caption and an opt-in animation control.
- `GameWorld.tsx`: legacy prop and snapshot compatibility bridge.

The Office tab is optional; Inbox remains the initial tab. Animation defaults off and reduced-motion preferences override animation. Hidden, offscreen and unmounted scenes stop animation and release resources. Device pixel ratio is capped at two. Character location is illustrative, not a tracking feed; disconnected status does not invent active work.

## Acceptance

- Production frontend compiles and builds.
- Office is reachable through the active dashboard, not only the legacy app.
- Desktop and mobile scenes contain real rendered furniture, readable controls and no horizontal overflow.
- Screenshots are captured from the running application and reviewed visually.
- Default static rendering, opt-in animation, reduced motion and repeated tab unmounts are exercised in a real browser.

Verification artifacts live in `C:/Users/pc/AppData/Local/Temp/drift-complete-zhf20q5y`; acceptance items above are criteria, not an assertion that an unrun check passed.
