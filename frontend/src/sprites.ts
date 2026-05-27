/**
 * Sprite data for image-based rendering (Smallville-style assets).
 * Character sprite sheet: 96x128 PNG, 32x32 frames.
 * Room background: pre-rendered tilemap PNG.
 */

// Room dimensions in tiles
export const COLS = 12;
export const ROWS = 12;
export const TILE = 32; // pixels per tile

// Character sprite frames (48x48 each in a 144x192 sheet)
// Layout: 3 cols x 4 rows. Walk sequence is frame 0,1,2,1.
export const CHAR_SIZE = 48;
export const FRAMES: Record<string, { x: number; y: number }[]> = {
  down:  [{ x: 0, y: 0 },   { x: 48, y: 0 },   { x: 96, y: 0 }],
  left:  [{ x: 0, y: 48 },  { x: 48, y: 48 },  { x: 96, y: 48 }],
  right: [{ x: 0, y: 96 },  { x: 48, y: 96 },  { x: 96, y: 96 }],
  up:    [{ x: 0, y: 144 }, { x: 48, y: 144 }, { x: 96, y: 144 }],
};

// Walk animation sequence indices into FRAMES arrays
export const WALK_SEQ = [0, 1, 2, 1];

// Idle frame index (standing still)
export const IDLE_FRAME = 1;

// Named locations (tile coordinates within 12x12 room)
export const LOCATIONS: Record<string, { x: number; y: number }> = {
  desk: { x: 10, y: 1 },
  bookshelf: { x: 1, y: 2 },
  window: { x: 4, y: 0 },
  plant: { x: 0, y: 8 },
  bed: { x: 3, y: 10 },
  rug: { x: 5, y: 5 },
  center: { x: 5, y: 5 },
};
