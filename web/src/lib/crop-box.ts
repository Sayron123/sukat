export type CropBox = { x: number; y: number; w: number; h: number };

export type Handle = "move" | "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se";

export const WHOLE_PHOTO: CropBox = { x: 0, y: 0, w: 1, h: 1 };
export const MIN_SIDE = 0.1;

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

export function dragBox(start: CropBox, handle: Handle, dx: number, dy: number): CropBox {
  if (handle === "move") {
    return { ...start, x: clamp(start.x + dx, 0, 1 - start.w), y: clamp(start.y + dy, 0, 1 - start.h) };
  }
  let left = start.x;
  let top = start.y;
  let right = start.x + start.w;
  let bottom = start.y + start.h;
  if (handle.includes("w")) left = clamp(left + dx, 0, right - MIN_SIDE);
  if (handle.includes("e")) right = clamp(right + dx, left + MIN_SIDE, 1);
  if (handle.includes("n")) top = clamp(top + dy, 0, bottom - MIN_SIDE);
  if (handle.includes("s")) bottom = clamp(bottom + dy, top + MIN_SIDE, 1);
  return { x: left, y: top, w: right - left, h: bottom - top };
}

export function cropPixels(box: CropBox, width: number, height: number) {
  const left = clamp(Math.round(box.x * width), 0, width - 1);
  const top = clamp(Math.round(box.y * height), 0, height - 1);
  const right = clamp(Math.round((box.x + box.w) * width), left + 1, width);
  const bottom = clamp(Math.round((box.y + box.h) * height), top + 1, height);
  return { sx: left, sy: top, sw: right - left, sh: bottom - top };
}
