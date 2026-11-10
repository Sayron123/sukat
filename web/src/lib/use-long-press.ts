"use client";

import { useEffect, useRef, type MouseEvent, type PointerEvent } from "react";

const HOLD_MS = 500;
const MOVE_LIMIT_PX = 10;
const CLICK_AFTER_HOLD_MS = 350;

export function useLongPress() {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const origin = useRef({ x: 0, y: 0 });
  const touch = useRef(false);
  const held = useRef(false);

  function cancel() {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }

  function release() {
    setTimeout(() => {
      held.current = false;
    }, CLICK_AFTER_HOLD_MS);
  }

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  return {
    handlers: (onLongPress: () => void) => ({
      onPointerDown(e: PointerEvent) {
        if (e.button !== 0) return;
        touch.current = e.pointerType !== "mouse";
        origin.current = { x: e.clientX, y: e.clientY };
        cancel();
        timer.current = setTimeout(() => {
          timer.current = null;
          held.current = true;
          window.addEventListener("pointerup", release, { once: true });
          window.addEventListener("pointercancel", release, { once: true });
          onLongPress();
        }, HOLD_MS);
      },
      onPointerMove(e: PointerEvent) {
        if (Math.hypot(e.clientX - origin.current.x, e.clientY - origin.current.y) > MOVE_LIMIT_PX) cancel();
      },
      onPointerUp: cancel,
      onPointerCancel: cancel,
      onPointerLeave: cancel,
      onContextMenu(e: MouseEvent) {
        if (touch.current) e.preventDefault();
      },
    }),
    isHolding: () => held.current,
  };
}
