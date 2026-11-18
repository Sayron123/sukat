import Image from "next/image";

const MIN_HEIGHT = 28;

export function SukatLogo({ height = 32, className = "" }: { height?: number; className?: string }) {
  const h = Math.max(height, MIN_HEIGHT);
  const w = Math.round((h * 345) / 98);
  const size = { width: w, height: h, fetchPriority: "high" } as const;

  return (
    <span className={`inline-flex shrink-0 ${className}`} style={{ width: w, height: h }}>
      <Image src="/mascot/sukat-logo-pullout-light.svg" alt="Sukat" {...size} className="dark:hidden" />
      <Image src="/mascot/sukat-logo-pullout-dark.svg" alt="Sukat" {...size} className="hidden dark:block" />
    </span>
  );
}
