import { type CropBox, WHOLE_PHOTO, cropPixels } from "./crop-box";

/**
 * Cut out `crop` (fractions of the upright photo), then shrink it before upload: longest
 * side at most `maxSide` px, JPEG at `quality`. A 12 MP photo (~4 MB) becomes ~250-400 KB:
 * faster on mobile data, and still sharp enough for the AI to read handwriting.
 *
 * Respects EXIF rotation (imageOrientation: "from-image"), so portrait photos stay upright.
 * @throws Error if the file can't be decoded as an image
 */
export async function compressImage(
  file: Blob,
  crop: CropBox = WHOLE_PHOTO,
  maxSide = 1600,
  quality = 0.7,
): Promise<Blob> {
  const source = await decode(file);
  const { sx, sy, sw, sh } = cropPixels(crop, source.width, source.height);
  const scale = Math.min(1, maxSide / Math.max(sw, sh));
  const width = Math.round(sw * scale);
  const height = Math.round(sh * scale);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas is not supported");
  ctx.fillStyle = "#FFFFFF"; // transparent PNGs become white, not black
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(source.image, sx, sy, sw, sh, 0, 0, width, height);
  source.close();

  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  if (!blob) throw new Error("Could not compress the photo");
  return blob;
}

type Decoded = { image: CanvasImageSource; width: number; height: number; close: () => void };

async function decode(file: Blob): Promise<Decoded> {
  if (typeof createImageBitmap === "function") {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
      return { image: bmp, width: bmp.width, height: bmp.height, close: () => bmp.close() };
    } catch {
      // Some older browsers reject the options object; fall back to <img>.
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return { image: img, width: img.naturalWidth, height: img.naturalHeight, close: () => {} };
  } catch {
    throw new Error("This file is not a photo we can read");
  } finally {
    URL.revokeObjectURL(url);
  }
}
