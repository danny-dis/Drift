/**
 * Procedural pixel-art pet sprites.
 * Each pet type is drawn with colored rectangles on canvas.
 * No image assets needed — pure canvas drawing.
 */

type Ctx = CanvasRenderingContext2D;

interface PetDef {
  bodyColor: string;
  bellyColor: string;
  earColor: string;
  eyeColor: string;
  noseColor: string;
  draw: (ctx: Ctx, x: number, y: number, size: number, frame: number) => void;
}

const P = 3; // pixel size (each "pixel" is 3x3 real pixels)

function px(ctx: Ctx, x: number, y: number, w: number, h: number, color: string) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w * P, h * P);
}

// --- Cat ---
const cat: PetDef = {
  bodyColor: "#f5a623",
  bellyColor: "#fff3e0",
  earColor: "#e8941a",
  eyeColor: "#2c2c2c",
  noseColor: "#ff8a80",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;

    // Body
    px(ctx, cx - 5 * P, baseY + 4 * P + bounce, 10, 8, cat.bodyColor);
    // Belly
    px(ctx, cx - 3 * P, baseY + 6 * P + bounce, 6, 4, cat.bellyColor);
    // Head
    px(ctx, cx - 4 * P, baseY - 2 * P + bounce, 8, 7, cat.bodyColor);
    // Ears (pointy)
    px(ctx, cx - 4 * P, baseY - 4 * P + bounce, 2, 3, cat.earColor);
    px(ctx, cx + 2 * P, baseY - 4 * P + bounce, 2, 3, cat.earColor);
    // Inner ears
    px(ctx, cx - 3 * P, baseY - 3 * P + bounce, 1, 1, "#ffb6c1");
    px(ctx, cx + 2 * P, baseY - 3 * P + bounce, 1, 1, "#ffb6c1");
    // Eyes
    px(ctx, cx - 3 * P, baseY + 0 * P + bounce, 2, 2, cat.eyeColor);
    px(ctx, cx + 1 * P, baseY + 0 * P + bounce, 2, 2, cat.eyeColor);
    // Eye shine
    px(ctx, cx - 2 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    px(ctx, cx + 2 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    // Nose
    px(ctx, cx - 0.5 * P, baseY + 2 * P + bounce, 1, 1, cat.noseColor);
    // Mouth
    px(ctx, cx - 1 * P, baseY + 3 * P + bounce, 1, 1, "#d4845e");
    px(ctx, cx + 0 * P, baseY + 3 * P + bounce, 1, 1, "#d4845e");
    // Legs
    px(ctx, cx - 4 * P, baseY + 11 * P + bounce, 2, 3, cat.bodyColor);
    px(ctx, cx + 2 * P, baseY + 11 * P + bounce, 2, 3, cat.bodyColor);
    // Tail
    const tailWag = frame % 4 < 2 ? 0 : P;
    px(ctx, cx + 5 * P, baseY + 5 * P + bounce + tailWag, 1, 1, cat.bodyColor);
    px(ctx, cx + 6 * P, baseY + 4 * P + bounce + tailWag, 1, 1, cat.bodyColor);
    px(ctx, cx + 7 * P, baseY + 3 * P + bounce + tailWag, 1, 1, cat.bodyColor);
    // Whiskers
    px(ctx, cx - 6 * P, baseY + 1 * P + bounce, 2, 1, "#ccc");
    px(ctx, cx + 4 * P, baseY + 1 * P + bounce, 2, 1, "#ccc");
  },
};

// --- Dog ---
const dog: PetDef = {
  bodyColor: "#8d6e4a",
  bellyColor: "#d4b896",
  earColor: "#6b4f32",
  eyeColor: "#2c2c2c",
  noseColor: "#1a1a1a",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;

    // Body
    px(ctx, cx - 5 * P, baseY + 4 * P + bounce, 10, 8, dog.bodyColor);
    // Belly
    px(ctx, cx - 3 * P, baseY + 6 * P + bounce, 6, 4, dog.bellyColor);
    // Head
    px(ctx, cx - 4 * P, baseY - 2 * P + bounce, 8, 7, dog.bodyColor);
    // Snout
    px(ctx, cx - 2 * P, baseY + 2 * P + bounce, 4, 3, dog.bellyColor);
    // Floppy ears
    px(ctx, cx - 5 * P, baseY - 1 * P + bounce, 2, 5, dog.earColor);
    px(ctx, cx + 3 * P, baseY - 1 * P + bounce, 2, 5, dog.earColor);
    // Eyes
    px(ctx, cx - 3 * P, baseY + 0 * P + bounce, 2, 2, dog.eyeColor);
    px(ctx, cx + 1 * P, baseY + 0 * P + bounce, 2, 2, dog.eyeColor);
    // Eye shine
    px(ctx, cx - 2 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    px(ctx, cx + 2 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    // Nose
    px(ctx, cx - 1 * P, baseY + 2 * P + bounce, 2, 2, dog.noseColor);
    // Legs
    px(ctx, cx - 4 * P, baseY + 11 * P + bounce, 2, 3, dog.bodyColor);
    px(ctx, cx + 2 * P, baseY + 11 * P + bounce, 2, 3, dog.bodyColor);
    // Tail (wagging)
    const wag = frame % 4 < 2 ? -P : P;
    px(ctx, cx + 5 * P, baseY + 4 * P + bounce + wag, 1, 1, dog.bodyColor);
    px(ctx, cx + 6 * P, baseY + 3 * P + bounce + wag, 1, 1, dog.bodyColor);
    px(ctx, cx + 6 * P, baseY + 2 * P + bounce + wag, 1, 1, dog.bodyColor);
    // Tongue (when walking)
    if (frame % 2 === 1) {
      px(ctx, cx - 0.5 * P, baseY + 5 * P + bounce, 1, 2, "#ff6b8a");
    }
  },
};

// --- Hamster ---
const hamster: PetDef = {
  bodyColor: "#f0c87a",
  bellyColor: "#fff8e8",
  earColor: "#e8b05c",
  eyeColor: "#1a1a1a",
  noseColor: "#ff8a80",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;
    const scrunch = frame % 2 === 0 ? 0 : P;

    // Body (round!)
    px(ctx, cx - 5 * P, baseY + 2 * P + bounce, 10, 10, hamster.bodyColor);
    // Cheeks (puffy)
    px(ctx, cx - 6 * P, baseY + 3 * P + bounce, 2, 4, "#f5d9a0");
    px(ctx, cx + 4 * P, baseY + 3 * P + bounce, 2, 4, "#f5d9a0");
    // Belly
    px(ctx, cx - 3 * P, baseY + 5 * P + bounce, 6, 5, hamster.bellyColor);
    // Head
    px(ctx, cx - 3 * P, baseY - 1 * P + bounce, 6, 5, hamster.bodyColor);
    // Tiny round ears
    px(ctx, cx - 3 * P, baseY - 3 * P + bounce, 2, 2, hamster.earColor);
    px(ctx, cx + 1 * P, baseY - 3 * P + bounce, 2, 2, hamster.earColor);
    // Eyes (big and round)
    px(ctx, cx - 2 * P, baseY + 0 * P + bounce, 2, 2, hamster.eyeColor);
    px(ctx, cx + 1 * P, baseY + 0 * P + bounce, 2, 2, hamster.eyeColor);
    // Eye shine
    px(ctx, cx - 1 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    px(ctx, cx + 2 * P, baseY + 0 * P + bounce, 1, 1, "#fff");
    // Nose
    px(ctx, cx - 0.5 * P, baseY + 2 * P + bounce, 1, 1, hamster.noseColor);
    // Tiny paws
    px(ctx, cx - 4 * P, baseY + 11 * P + scrunch, 2, 2, hamster.bodyColor);
    px(ctx, cx + 2 * P, baseY + 11 * P + scrunch, 2, 2, hamster.bodyColor);
    // Seed (when idle)
    if (frame === 0) {
      px(ctx, cx - 1 * P, baseY + 6 * P + bounce, 2, 2, "#8B7355");
    }
  },
};

// --- Owl ---
const owl: PetDef = {
  bodyColor: "#8b6914",
  bellyColor: "#f5e6c8",
  earColor: "#6b4f12",
  eyeColor: "#ffd700",
  noseColor: "#d4a017",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;
    const blink = frame % 8 === 4;

    // Body
    px(ctx, cx - 4 * P, baseY + 3 * P + bounce, 8, 9, owl.bodyColor);
    // Belly pattern
    px(ctx, cx - 3 * P, baseY + 5 * P + bounce, 6, 5, owl.bellyColor);
    // Belly stripes
    for (let i = 0; i < 3; i++) {
      px(ctx, cx - 2 * P, baseY + (6 + i * 2) * P + bounce, 4, 1, "#e0d0a8");
    }
    // Head (wide)
    px(ctx, cx - 5 * P, baseY - 2 * P + bounce, 10, 6, owl.bodyColor);
    // Ear tufts
    px(ctx, cx - 5 * P, baseY - 5 * P + bounce, 2, 4, owl.earColor);
    px(ctx, cx + 3 * P, baseY - 5 * P + bounce, 2, 4, owl.earColor);
    // Face disc (lighter)
    px(ctx, cx - 4 * P, baseY - 1 * P + bounce, 8, 5, "#c4a44a");
    // Eyes (huge)
    if (!blink) {
      px(ctx, cx - 3 * P, baseY + 0 * P + bounce, 3, 3, owl.eyeColor);
      px(ctx, cx + 0 * P, baseY + 0 * P + bounce, 3, 3, owl.eyeColor);
      // Pupils
      px(ctx, cx - 2 * P, baseY + 1 * P + bounce, 1, 1, "#1a1a1a");
      px(ctx, cx + 1 * P, baseY + 1 * P + bounce, 1, 1, "#1a1a1a");
    } else {
      px(ctx, cx - 3 * P, baseY + 1 * P + bounce, 3, 1, owl.eyeColor);
      px(ctx, cx + 0 * P, baseY + 1 * P + bounce, 3, 1, owl.eyeColor);
    }
    // Beak
    px(ctx, cx - 0.5 * P, baseY + 3 * P + bounce, 1, 2, owl.noseColor);
    // Wings (tucked)
    px(ctx, cx - 5 * P, baseY + 4 * P + bounce, 1, 6, owl.earColor);
    px(ctx, cx + 4 * P, baseY + 4 * P + bounce, 1, 6, owl.earColor);
    // Talons
    px(ctx, cx - 2 * P, baseY + 11 * P + bounce, 1, 2, owl.noseColor);
    px(ctx, cx + 1 * P, baseY + 11 * P + bounce, 1, 2, owl.noseColor);
    // Head bob when walking
    if (frame % 2 === 1) {
      px(ctx, cx - 0.5 * P, baseY + 4 * P + bounce, 1, 1, owl.bellyColor);
    }
  },
};

// --- Fox ---
const fox: PetDef = {
  bodyColor: "#e86a17",
  bellyColor: "#fff3e0",
  earColor: "#cc5500",
  eyeColor: "#2c2c2c",
  noseColor: "#1a1a1a",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;

    // Body
    px(ctx, cx - 5 * P, baseY + 4 * P + bounce, 10, 8, fox.bodyColor);
    // Belly
    px(ctx, cx - 3 * P, baseY + 6 * P + bounce, 6, 4, fox.bellyColor);
    // Head (pointed)
    px(ctx, cx - 4 * P, baseY - 2 * P + bounce, 8, 7, fox.bodyColor);
    // Snout (pointed)
    px(ctx, cx - 2 * P, baseY + 2 * P + bounce, 4, 3, fox.bellyColor);
    px(ctx, cx - 1 * P, baseY + 4 * P + bounce, 2, 1, fox.bellyColor);
    // Big pointed ears
    px(ctx, cx - 4 * P, baseY - 5 * P + bounce, 2, 4, fox.earColor);
    px(ctx, cx + 2 * P, baseY - 5 * P + bounce, 2, 4, fox.earColor);
    // Inner ears
    px(ctx, cx - 3 * P, baseY - 4 * P + bounce, 1, 2, "#fff3e0");
    px(ctx, cx + 2 * P, baseY - 4 * P + bounce, 1, 2, "#fff3e0");
    // Eyes (sly)
    px(ctx, cx - 3 * P, baseY + 0 * P + bounce, 2, 1, fox.eyeColor);
    px(ctx, cx + 1 * P, baseY + 0 * P + bounce, 2, 1, fox.eyeColor);
    // Nose
    px(ctx, cx - 0.5 * P, baseY + 3 * P + bounce, 1, 1, fox.noseColor);
    // Legs
    px(ctx, cx - 4 * P, baseY + 11 * P + bounce, 2, 3, fox.bodyColor);
    px(ctx, cx + 2 * P, baseY + 11 * P + bounce, 2, 3, fox.bodyColor);
    // Bushy tail
    const tailWag = frame % 4 < 2 ? 0 : P;
    px(ctx, cx + 5 * P, baseY + 5 * P + bounce + tailWag, 2, 2, fox.bodyColor);
    px(ctx, cx + 7 * P, baseY + 4 * P + bounce + tailWag, 2, 2, fox.bodyColor);
    px(ctx, cx + 8 * P, baseY + 3 * P + bounce + tailWag, 2, 1, "#fff3e0");
  },
};

// --- Rabbit ---
const rabbit: PetDef = {
  bodyColor: "#e8ddd0",
  bellyColor: "#fff",
  earColor: "#d4c4b0",
  eyeColor: "#cc3366",
  noseColor: "#ffb6c1",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;
    const earTwitch = frame % 4 < 2 ? 0 : P;

    // Body (round)
    px(ctx, cx - 5 * P, baseY + 4 * P + bounce, 10, 8, rabbit.bodyColor);
    // Belly
    px(ctx, cx - 3 * P, baseY + 6 * P + bounce, 6, 4, rabbit.bellyColor);
    // Head
    px(ctx, cx - 4 * P, baseY - 1 * P + bounce, 8, 6, rabbit.bodyColor);
    // Long ears!
    px(ctx, cx - 3 * P, baseY - 8 * P + bounce + earTwitch, 2, 8, rabbit.earColor);
    px(ctx, cx + 1 * P, baseY - 8 * P + bounce - earTwitch, 2, 8, rabbit.earColor);
    // Inner ears
    px(ctx, cx - 2 * P, baseY - 7 * P + bounce + earTwitch, 1, 6, "#ffb6c1");
    px(ctx, cx + 1 * P, baseY - 7 * P + bounce - earTwitch, 1, 6, "#ffb6c1");
    // Eyes
    px(ctx, cx - 3 * P, baseY + 1 * P + bounce, 2, 2, rabbit.eyeColor);
    px(ctx, cx + 1 * P, baseY + 1 * P + bounce, 2, 2, rabbit.eyeColor);
    // Eye shine
    px(ctx, cx - 2 * P, baseY + 1 * P + bounce, 1, 1, "#fff");
    px(ctx, cx + 2 * P, baseY + 1 * P + bounce, 1, 1, "#fff");
    // Nose (twitching)
    px(ctx, cx - 0.5 * P, baseY + 3 * P + bounce, 1, 1, rabbit.noseColor);
    // Whiskers
    px(ctx, cx - 6 * P, baseY + 2 * P + bounce, 2, 1, "#ccc");
    px(ctx, cx + 4 * P, baseY + 2 * P + bounce, 2, 1, "#ccc");
    // Legs (back legs bigger)
    px(ctx, cx - 4 * P, baseY + 11 * P + bounce, 2, 3, rabbit.bodyColor);
    px(ctx, cx + 2 * P, baseY + 11 * P + bounce, 3, 3, rabbit.bodyColor);
    // Cotton tail
    px(ctx, cx + 5 * P, baseY + 7 * P + bounce, 2, 2, "#fff");
  },
};

// --- Octopus ---
const octopus: PetDef = {
  bodyColor: "#9b59b6",
  bellyColor: "#d7bde2",
  earColor: "#8e44ad",
  eyeColor: "#fff",
  noseColor: "#e8a0bf",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.25;
    const bounce = frame % 2 === 0 ? 0 : -P;
    const wave = frame % 4;

    // Head (big round)
    px(ctx, cx - 5 * P, baseY + bounce, 10, 8, octopus.bodyColor);
    // Lighter top
    px(ctx, cx - 4 * P, baseY + bounce, 8, 3, "#a96bc4");
    // Belly
    px(ctx, cx - 3 * P, baseY + 3 * P + bounce, 6, 4, octopus.bellyColor);
    // Eyes (big)
    px(ctx, cx - 3 * P, baseY + 3 * P + bounce, 3, 3, octopus.eyeColor);
    px(ctx, cx + 1 * P, baseY + 3 * P + bounce, 3, 3, octopus.eyeColor);
    // Pupils
    px(ctx, cx - 2 * P, baseY + 4 * P + bounce, 1, 1, "#2c2c2c");
    px(ctx, cx + 2 * P, baseY + 4 * P + bounce, 1, 1, "#2c2c2c");
    // Tentacles (8 of them, animated)
    const tentacleColors = [octopus.bodyColor, octopus.earColor];
    for (let i = 0; i < 8; i++) {
      const tx = cx - 7 * P + i * 2 * P;
      const tColor = tentacleColors[i % 2];
      const tWave = ((wave + i) % 4) - 2;
      // Each tentacle is 3 segments
      px(ctx, tx, baseY + 8 * P + bounce, 1, 2, tColor);
      px(ctx, tx + tWave * P, baseY + 10 * P + bounce, 1, 2, tColor);
      px(ctx, tx + tWave * P * 2, baseY + 12 * P + bounce, 1, 1, tColor);
    }
    // Suckers (dots on tentacles)
    for (let i = 0; i < 4; i++) {
      const sx = cx - 6 * P + i * 3 * P;
      px(ctx, sx, baseY + 9 * P + bounce, 1, 1, octopus.noseColor);
    }
  },
};

// --- Penguin ---
const penguin: PetDef = {
  bodyColor: "#2c3e50",
  bellyColor: "#ecf0f1",
  earColor: "#2c3e50",
  eyeColor: "#fff",
  noseColor: "#f39c12",
  draw(ctx, x, y, size, frame) {
    const cx = x + size / 2;
    const baseY = y + size * 0.35;
    const bounce = frame % 2 === 0 ? 0 : -P;
    const waddle = frame % 4 < 2 ? 0 : P;

    // Body (oval)
    px(ctx, cx - 4 * P, baseY + 2 * P + bounce, 8, 10, penguin.bodyColor);
    // White belly
    px(ctx, cx - 3 * P, baseY + 3 * P + bounce, 6, 8, penguin.bellyColor);
    // Head
    px(ctx, cx - 4 * P, baseY - 2 * P + bounce, 8, 5, penguin.bodyColor);
    // White face patches
    px(ctx, cx - 3 * P, baseY - 1 * P + bounce, 2, 2, penguin.bellyColor);
    px(ctx, cx + 1 * P, baseY - 1 * P + bounce, 2, 2, penguin.bellyColor);
    // Eyes
    px(ctx, cx - 2 * P, baseY + 0 * P + bounce, 2, 2, penguin.eyeColor);
    px(ctx, cx + 1 * P, baseY + 0 * P + bounce, 2, 2, penguin.eyeColor);
    // Pupils
    px(ctx, cx - 1 * P, baseY + 0 * P + bounce, 1, 1, "#1a1a1a");
    px(ctx, cx + 2 * P, baseY + 0 * P + bounce, 1, 1, "#1a1a1a");
    // Beak
    px(ctx, cx - 0.5 * P, baseY + 2 * P + bounce, 1, 1, penguin.noseColor);
    px(ctx, cx - 1 * P, baseY + 3 * P + bounce, 2, 1, penguin.noseColor);
    // Wings (flapping)
    px(ctx, cx - 5 * P, baseY + 3 * P + bounce + waddle, 1, 5, penguin.bodyColor);
    px(ctx, cx + 4 * P, baseY + 3 * P + bounce - waddle, 1, 5, penguin.bodyColor);
    // Feet
    px(ctx, cx - 3 * P, baseY + 11 * P + bounce, 2, 2, penguin.noseColor);
    px(ctx, cx + 1 * P, baseY + 11 * P + bounce, 2, 2, penguin.noseColor);
  },
};

// --- Registry ---
const PETS: Record<string, PetDef> = {
  cat, dog, hamster, owl, fox, rabbit, octopus, penguin,
};

/**
 * Draw a pet at the given position.
 * Falls back to cat if the pet type isn't recognized.
 */
export function drawPet(
  ctx: CanvasRenderingContext2D,
  petType: string,
  x: number,
  y: number,
  size: number,
  frame: number,
) {
  const pet = PETS[petType] || cat;
  pet.draw(ctx, x, y, size, frame);
}

/**
 * Get available pet types for UI selection.
 */
export function getPetTypes(): string[] {
  return Object.keys(PETS);
}
