import Link from "next/link";
import type { ReactNode } from "react";

import { Icon } from "./icons";

export const backClass = "-ml-2 grid h-11 w-11 shrink-0 place-items-center rounded-button text-text hover:bg-surface";

/**
 * Sticky screen header: small uppercase line above a bold title, optional back arrow
 * (a link `back`, or a button `onBack`) and an optional action on the right.
 * Must sit directly inside AppPage's padded column.
 */
export function PageHeader({
  title,
  eyebrow,
  back,
  onBack,
  action,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  back?: string;
  onBack?: () => void;
  action?: ReactNode;
}) {
  return (
    <header className="sticky top-0 z-10 -mx-5 mb-5 flex min-h-[88px] items-center justify-between gap-3 bg-background px-5 pt-[22px] pb-3.5">
      <div className="flex min-w-0 items-center gap-2.5">
        {back && (
          <Link href={back} aria-label="Go back" className={backClass}>
            <Icon name="arrow" />
          </Link>
        )}
        {onBack && !back && (
          <button type="button" onClick={onBack} aria-label="Go back" className={backClass}>
            <Icon name="arrow" />
          </button>
        )}
        <div className="min-w-0">
          {eyebrow && <p className="truncate text-[13px] font-bold text-muted uppercase">{eyebrow}</p>}
          <h1 className="mt-0.5 truncate text-[22px] leading-tight font-bold text-text">{title}</h1>
        </div>
      </div>
      {action}
    </header>
  );
}

/** Round 44px icon button for the header's right side. */
export const headerIconClass = "grid h-11 w-11 shrink-0 place-items-center rounded-button text-text hover:bg-surface";
