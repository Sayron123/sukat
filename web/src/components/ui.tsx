import type { ComponentProps, ReactNode } from "react";

import { Icon, type IconName } from "./icons";

/** White card with a light border (product rows, review lines, lists). */
export function Card({
  className = "",
  padded = true,
  ...props
}: ComponentProps<"div"> & { padded?: boolean }) {
  return (
    <div
      className={`rounded-card border border-border bg-background ${padded ? "p-4" : ""} ${className}`}
      {...props}
    />
  );
}

/** Grey info box with an optional icon and bold title. */
export function Notice({
  icon,
  title,
  children,
  className = "",
  ...props
}: Omit<ComponentProps<"div">, "title"> & { icon?: IconName; title?: ReactNode }) {
  return (
    <div className={`flex gap-3 rounded-card bg-surface p-4 text-sm ${className}`} {...props}>
      {icon && <Icon name={icon} size={20} className="mt-px" />}
      <div className="min-w-0">
        {title && <p className="font-bold text-text">{title}</p>}
        {children && <div className={`leading-snug text-muted ${title ? "mt-1" : ""}`}>{children}</div>}
      </div>
    </div>
  );
}

const BADGE_TONES = {
  red: "border-[#fecaca] bg-[#fef2f2] text-red",
  amber: "border-[#fde68a] bg-[#fffbeb] text-[#b45309]",
  green: "border-[#bbf7d0] bg-[#f0fdf4] text-[#15803d]",
  neutral: "border-border bg-surface text-muted",
} as const;

export function Badge({
  tone = "neutral",
  className = "",
  ...props
}: ComponentProps<"span"> & { tone?: keyof typeof BADGE_TONES }) {
  return (
    <span
      className={`inline-flex min-h-6 shrink-0 items-center justify-center whitespace-nowrap rounded-full border px-2.5 text-[13px] leading-none font-bold ${BADGE_TONES[tone]} ${className}`}
      {...props}
    />
  );
}

const BUTTON_COLORS = {
  primary: "bg-accent shadow-[0_2px_4px_rgba(124,45,18,0.15)] hover:bg-accent-pressed active:bg-accent-pressed",
  danger: "bg-red hover:bg-red/90 active:bg-red/90",
  success: "bg-green",
} as const;

const BUTTON_SIZES = { md: "h-12 text-[15px]", lg: "h-14 text-base" } as const;

/** Class names for a filled button, also used to style links as buttons. */
export function buttonClass(
  variant: keyof typeof BUTTON_COLORS = "primary",
  size: keyof typeof BUTTON_SIZES = "md",
) {
  return `flex w-full items-center justify-center gap-2.5 rounded-button px-4 font-bold text-white active:translate-y-px disabled:opacity-45 ${BUTTON_SIZES[size]} ${BUTTON_COLORS[variant]}`;
}

/** Filled button. Use `variant` for color (passing bg-* classes would conflict). */
export function Button({
  className = "",
  variant = "primary",
  size = "md",
  icon,
  children,
  ...props
}: ComponentProps<"button"> & {
  variant?: keyof typeof BUTTON_COLORS;
  size?: keyof typeof BUTTON_SIZES;
  icon?: IconName;
}) {
  return (
    <button className={`${buttonClass(variant, size)} ${className}`} {...props}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

/** Class names for an outlined button, also used to style links as buttons. */
export const ghostButtonClass =
  "flex h-12 items-center justify-center gap-2 rounded-button border border-line bg-background px-4 text-[15px] font-semibold text-muted hover:bg-surface disabled:opacity-45";

/** Secondary (outlined) button. */
export function GhostButton({ className = "", ...props }: ComponentProps<"button">) {
  return <button className={`${ghostButtonClass} ${className}`} {...props} />;
}

/** Underlined grey text button ("Start over", "New store? Sign up here"). */
export const textLinkClass = "inline-flex min-h-11 items-center text-[13px] text-muted underline";

/**
 * Labelled input. `prefix`/`suffix` show inside the box (₱, units). `compact` is the small
 * style used in review lines (grey label, 42px box).
 */
export function Field({
  label,
  id,
  hint,
  prefix,
  suffix,
  invalid,
  compact = false,
  wrapperClassName = "",
  ...props
}: ComponentProps<"input"> & {
  label: string;
  id: string;
  hint?: ReactNode;
  prefix?: string;
  suffix?: string;
  invalid?: boolean;
  compact?: boolean;
  wrapperClassName?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col ${wrapperClassName}`}>
      <label
        htmlFor={id}
        className={compact ? "mb-1.5 text-[13px] text-subtle" : "mb-[7px] text-[13px] font-bold text-text"}
      >
        {label}
      </label>
      <div
        className={`flex w-full min-w-0 items-center overflow-hidden rounded-button border bg-background focus-within:ring-1 ${
          compact ? "h-[42px]" : "h-12"
        } ${invalid ? "border-red focus-within:ring-red" : "border-line focus-within:border-text focus-within:ring-text"}`}
      >
        {prefix && <span className="pl-3 text-sm text-muted">{prefix}</span>}
        <input
          id={id}
          aria-invalid={invalid || undefined}
          className={`h-full w-full min-w-0 bg-transparent text-text outline-none placeholder:text-subtle ${
            compact ? "px-[7px] text-[13px] font-semibold" : "px-3"
          }`}
          {...props}
        />
        {suffix && <span className="pr-3 text-sm whitespace-nowrap text-muted">{suffix}</span>}
      </div>
      {hint && <p className="mt-1.5 text-[13px] leading-snug text-subtle">{hint}</p>}
    </div>
  );
}

export function Select({
  label,
  id,
  children,
  wrapperClassName = "",
  ...props
}: ComponentProps<"select"> & { label: string; id: string; wrapperClassName?: string }) {
  return (
    <div className={`flex min-w-0 flex-col ${wrapperClassName}`}>
      <label htmlFor={id} className="mb-[7px] text-[13px] font-bold text-text">
        {label}
      </label>
      <select
        id={id}
        className="h-12 w-full min-w-0 rounded-button border border-line bg-background px-3 text-text outline-none focus:border-text focus:ring-1 focus:ring-text"
        {...props}
      >
        {children}
      </select>
    </div>
  );
}

/** Search input with a magnifier icon. */
export function SearchBox({ className = "", ...props }: ComponentProps<"input">) {
  return (
    <div
      className={`flex h-12 items-center gap-2.5 rounded-button border border-line bg-background px-3.5 text-muted focus-within:border-text focus-within:ring-1 focus-within:ring-text ${className}`}
    >
      <Icon name="search" size={19} />
      <input
        type="search"
        className="h-full w-full min-w-0 bg-transparent text-[15px] text-text outline-none placeholder:text-subtle"
        {...props}
      />
    </div>
  );
}

export function Chip({
  selected,
  className = "",
  ...props
}: ComponentProps<"button"> & { selected: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`h-[38px] shrink-0 whitespace-nowrap rounded-button border px-3.5 text-[13px] font-semibold ${
        selected ? "border-text bg-text text-white" : "border-line bg-background text-muted hover:bg-surface"
      } ${className}`}
      {...props}
    />
  );
}

/** Round grey circle with initials. */
export function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return (
    <span
      aria-hidden
      className={`grid shrink-0 place-items-center rounded-full bg-border text-[13px] font-bold text-text ${
        large ? "h-12 w-12" : "h-[42px] w-[42px]"
      }`}
    >
      {initials(name)}
    </span>
  );
}

/** "Juan dela Cruz" -> "JC" (first and last word). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/** Previous / Page x of y / Next row. */
export function Pager({
  page,
  pages,
  onPage,
}: {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between gap-2">
      <GhostButton type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </GhostButton>
      <span className="text-sm text-muted">
        Page {page} of {pages}
      </span>
      <GhostButton type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </GhostButton>
    </div>
  );
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return <p className="pt-8 text-muted">{text}</p>;
}
