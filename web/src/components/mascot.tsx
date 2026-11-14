import Image from "next/image";
import type { ReactNode } from "react";

export const EMOTES = [
  "normal",
  "thinking",
  "happy",
  "confused",
  "error",
  "success",
  "warning",
  "offline",
  "empty",
  "sleeping",
  "searching",
  "locked",
  "scanning",
  "scan-blurry",
  "scan-done",
] as const;

export type Emote = (typeof EMOTES)[number];

const ALT: Record<Emote, string> = {
  normal: "Sukat mascot",
  thinking: "Sukat mascot, thinking",
  happy: "Sukat mascot, happy",
  confused: "Sukat mascot, confused",
  error: "Sukat mascot, something went wrong",
  success: "Sukat mascot, done",
  warning: "Sukat mascot, warning",
  offline: "Sukat mascot, offline",
  empty: "Sukat mascot, nothing here yet",
  sleeping: "Sukat mascot, sleeping",
  searching: "Sukat mascot, searching",
  locked: "Sukat mascot, locked",
  scanning: "Sukat mascot, scanning a receipt",
  "scan-blurry": "Sukat mascot, the photo is blurry",
  "scan-done": "Sukat mascot, scan done",
};

function src(emote: Emote, theme: "dark" | "light") {
  return `/mascot/emotes-svg/sukat-${emote}-${theme}.svg`;
}

export function Mascot({
  emote,
  size = 120,
  glow = false,
  alt,
  className = "",
}: {
  emote: Emote;
  size?: number;
  glow?: boolean;
  alt?: string;
  className?: string;
}) {
  const label = alt ?? ALT[emote];

  return (
    <span
      className={`relative inline-grid shrink-0 place-items-center ${className}`}
      style={{ width: size, height: size }}
    >
      {glow && (
        <span
          aria-hidden
          className="pointer-events-none absolute -inset-1/4 rounded-full"
          style={{ backgroundImage: "radial-gradient(closest-side, var(--color-glow), transparent)" }}
        />
      )}
      <Image src={src(emote, "light")} alt={label} width={size} height={size} className="relative dark:hidden" />
      <Image src={src(emote, "dark")} alt={label} width={size} height={size} className="relative hidden dark:block" />
    </span>
  );
}

export function MascotMessage({
  emote,
  title,
  children,
  size = 88,
  className = "",
}: {
  emote: Emote;
  title?: ReactNode;
  children?: ReactNode;
  size?: number;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center px-2 py-3 text-center ${className}`}>
      <Mascot emote={emote} size={size} alt="" />
      {title && <p className="mt-2 font-bold text-text">{title}</p>}
      {children && <div className={`text-sm text-muted ${title ? "mt-1" : "mt-2"}`}>{children}</div>}
    </div>
  );
}
