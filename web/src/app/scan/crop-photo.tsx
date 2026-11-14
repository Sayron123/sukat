"use client";

import Image from "next/image";
import { useRef, useState } from "react";

import { Icon } from "@/components/icons";
import { Button } from "@/components/ui";
import { type CropBox, type Handle, WHOLE_PHOTO, dragBox } from "@/lib/crop-box";

const KEY_STEP = 0.02;

const KEY_MOVES: Record<string, [number, number]> = {
  ArrowUp: [0, -KEY_STEP],
  ArrowDown: [0, KEY_STEP],
  ArrowLeft: [-KEY_STEP, 0],
  ArrowRight: [KEY_STEP, 0],
};

const HANDLES: { handle: Handle; label: string; place: string; mark: string }[] = [
  { handle: "nw", label: "Top left corner", place: "-top-5.5 -left-5.5 cursor-nwse-resize", mark: "h-5 w-5 rounded-full" },
  { handle: "ne", label: "Top right corner", place: "-top-5.5 -right-5.5 cursor-nesw-resize", mark: "h-5 w-5 rounded-full" },
  { handle: "sw", label: "Bottom left corner", place: "-bottom-5.5 -left-5.5 cursor-nesw-resize", mark: "h-5 w-5 rounded-full" },
  { handle: "se", label: "Bottom right corner", place: "-right-5.5 -bottom-5.5 cursor-nwse-resize", mark: "h-5 w-5 rounded-full" },
  { handle: "n", label: "Top edge", place: "-top-5.5 left-1/2 -translate-x-1/2 cursor-ns-resize", mark: "h-2 w-10 rounded-full" },
  { handle: "s", label: "Bottom edge", place: "-bottom-5.5 left-1/2 -translate-x-1/2 cursor-ns-resize", mark: "h-2 w-10 rounded-full" },
];

type Drag = { handle: Handle; pointerX: number; pointerY: number; start: CropBox; width: number; height: number };

const HANDLE_NAMES = new Set<string>(["move", ...HANDLES.map((h) => h.handle)]);

function handleOf(element: HTMLElement): Handle | null {
  const name = element.dataset.handle;
  return name && HANDLE_NAMES.has(name) ? (name as Handle) : null;
}

export function CropPhoto({
  title,
  photoUrl,
  onConfirm,
  onRetake,
}: {
  title: string;
  photoUrl: string;
  onConfirm: (box: CropBox) => void;
  onRetake: () => void;
}) {
  const [box, setBox] = useState<CropBox>(WHOLE_PHOTO);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);

  function begin(e: React.PointerEvent<HTMLElement>) {
    const handle = handleOf(e.currentTarget);
    const rect = frame.current?.getBoundingClientRect();
    if (!handle || !rect || rect.width === 0 || rect.height === 0) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { handle, pointerX: e.clientX, pointerY: e.clientY, start: box, width: rect.width, height: rect.height };
  }

  function follow(e: React.PointerEvent<HTMLElement>) {
    const d = drag.current;
    if (!d) return;
    e.stopPropagation();
    setBox(dragBox(d.start, d.handle, (e.clientX - d.pointerX) / d.width, (e.clientY - d.pointerY) / d.height));
  }

  function end() {
    drag.current = null;
  }

  function nudge(e: React.KeyboardEvent<HTMLElement>) {
    const handle = handleOf(e.currentTarget);
    const move = KEY_MOVES[e.key];
    if (!handle || !move) return;
    e.preventDefault();
    e.stopPropagation();
    setBox((current) => dragBox(current, handle, move[0], move[1]));
  }

  const place = {
    left: `${box.x * 100}%`,
    top: `${box.y * 100}%`,
    width: `${box.w * 100}%`,
    height: `${box.h * 100}%`,
  };
  const round = "grid h-11 w-11 place-items-center rounded-full bg-white/10 text-white";

  return (
    <div className="fixed inset-0 z-30 flex flex-col bg-dark text-white">
      <div className="mx-auto flex w-full max-w-lg flex-1 flex-col">
        <div className="grid h-22 grid-cols-[44px_1fr_44px] items-center gap-2 px-4 pt-4.5 pb-2.5">
          <button type="button" aria-label="Retake photo" onClick={onRetake} className={round}>
            <Icon name="close" />
          </button>
          <div className="text-center">
            <h1 className="text-base font-bold">{title}</h1>
            <p className="mt-0.75 text-[13px] text-bar-muted">Box only the items. Leave out the customer’s name.</p>
          </div>
          <span />
        </div>

        <div className="grid min-h-0 flex-1 place-items-center px-8 py-6">
          <div ref={frame} className="relative w-fit touch-none select-none">
            <Image
              src={photoUrl}
              alt="Your photo"
              width={1200}
              height={1600}
              unoptimized
              draggable={false}
              className="block h-auto max-h-[calc(100dvh-300px)] w-auto max-w-full rounded bg-white"
            />
            <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden rounded">
              <div className="absolute shadow-[0_0_0_9999px_rgba(12,10,9,0.65)]" style={place} />
            </div>
            <div
              role="group"
              aria-label="Part of the photo to read. Drag to move it, or drag a corner or edge to resize it."
              tabIndex={0}
              className="absolute cursor-move outline-2 outline-white focus-visible:outline-accent"
              style={place}
              data-handle="move"
              onPointerDown={begin}
              onPointerMove={follow}
              onPointerUp={end}
              onPointerCancel={end}
              onKeyDown={nudge}
            >
              {HANDLES.map(({ handle, label, place: spot, mark }) => (
                <button
                  key={handle}
                  type="button"
                  aria-label={label}
                  className={`absolute grid h-11 w-11 place-items-center ${spot}`}
                  data-handle={handle}
                  onPointerDown={begin}
                  onPointerMove={follow}
                  onPointerUp={end}
                  onPointerCancel={end}
                  onKeyDown={nudge}
                >
                  <span className={`block border-2 border-accent bg-white shadow ${mark}`} />
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 px-6 pt-2 pb-[max(28px,env(safe-area-inset-bottom))]">
          <button
            type="button"
            onClick={onRetake}
            className="flex h-14 items-center justify-center gap-2 rounded-button bg-white/10 text-base font-semibold text-white"
          >
            <Icon name="camera" size={20} />
            Retake
          </button>
          <Button size="lg" icon="check" onClick={() => onConfirm(box)}>
            Use this part
          </Button>
        </div>
      </div>
    </div>
  );
}
