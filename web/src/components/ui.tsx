import type { ComponentProps } from "react";

export function Card({
  className = "",
  padded = true,
  ...props
}: ComponentProps<"div"> & { padded?: boolean }) {
  return (
    <div
      className={`rounded-card border border-border bg-surface ${padded ? "p-6" : ""} ${className}`}
      {...props}
    />
  );
}

export function Button({ className = "", ...props }: ComponentProps<"button">) {
  return (
    <button
      className={`h-11 rounded-button bg-accent px-4 font-medium text-white hover:bg-accent-pressed active:bg-accent-pressed disabled:opacity-60 ${className}`}
      {...props}
    />
  );
}

export function Field({
  label,
  id,
  ...props
}: ComponentProps<"input"> & { label: string; id: string }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
      </label>
      <input
        id={id}
        className="h-11 rounded-button border border-border bg-background px-3 text-text outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
        {...props}
      />
    </div>
  );
}
