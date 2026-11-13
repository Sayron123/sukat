import { useId } from "react";

type Pose = "waving" | "thinking";

const POSES = {
  waving: {
    arm: "M84 84 C100 84 106 72 104 50",
    tip: { x: 96, y: 44 },
    eyes: [43, 60, 65, 60],
  },
  thinking: {
    arm: "M84 84 C98 84 104 78 104 66",
    tip: { x: 96, y: 60 },
    eyes: [46, 57, 68, 57],
  },
} as const;

const INK = "#1C1917";

export function SukatMascot({
  pose,
  size = 120,
  label,
  className = "",
}: {
  pose: Pose;
  size?: number;
  label?: string;
  className?: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const thinking = pose === "thinking";
  const { arm, tip, eyes } = POSES[pose];

  return (
    <svg
      viewBox="-7 -7 134 134"
      width={size}
      height={size}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={`block shrink-0 overflow-visible ${className}`}
    >
      <defs>
        <linearGradient id={`${id}c`} x1="0" y1="0" x2="0.3" y2="1">
          <stop offset="0" stopColor="#F97316" />
          <stop offset="0.55" stopColor="#C2410C" />
          <stop offset="1" stopColor="#9A3412" />
        </linearGradient>
        <radialGradient id={`${id}f`} cx="0.38" cy="0.32" r="0.75">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.7" stopColor="#F5F5F4" />
          <stop offset="1" stopColor="#D6D3D1" />
        </radialGradient>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#D6D3D1" />
        </linearGradient>
      </defs>

      <ellipse
        cx="56"
        cy="108"
        rx="38"
        ry="6"
        fillOpacity="0.15"
        className={`origin-[56px_108px] fill-text ${thinking ? "" : "motion-safe:animate-sukat-shadow"}`}
      />

      <g
        className={thinking ? "origin-[54px_100px] motion-safe:animate-sukat-sway" : "motion-safe:animate-sukat-float"}
      >
        <rect x="44" y="20" width="20" height="12" rx="4" fill="#44403C" />

        <g
          className={`origin-[84px_84px] ${thinking ? "motion-safe:animate-sukat-tap" : "motion-safe:animate-sukat-wave"}`}
        >
          <path d={arm} fill="none" stroke="#78716C" strokeWidth="13" />
          <path d={arm} fill="none" stroke={`url(#${id}b)`} strokeWidth="9" />
          <rect x={tip.x} y={tip.y} width="16" height="8" rx="2" fill={INK} />
          {!thinking && (
            <path
              d="M108 38 q4 -4 0 -9 M114 42 q5 -5 0 -12"
              fill="none"
              strokeWidth="3"
              strokeLinecap="round"
              className="stroke-text motion-safe:animate-sukat-ping"
            />
          )}
        </g>

        <rect x="20" y="34" width="68" height="66" rx="22" fill="#7C2D12" />
        <rect x="20" y="28" width="68" height="66" rx="22" fill={`url(#${id}c)`} stroke="#7C2D12" strokeWidth="2" />
        <path
          d="M30 42 Q34 33 44 32"
          fill="none"
          stroke="#FFFFFF"
          strokeOpacity="0.55"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle cx="54" cy="62" r="23" fill={`url(#${id}f)`} stroke="#7C2D12" strokeWidth="2.5" />

        <g className={thinking ? "motion-safe:animate-sukat-glance" : ""}>
          <g className="origin-center [transform-box:fill-box] motion-safe:animate-sukat-blink">
            <circle cx={eyes[0]} cy={eyes[1]} r="4.5" fill={INK} />
            <circle cx={eyes[2]} cy={eyes[3]} r="4.5" fill={INK} />
          </g>
        </g>
        {thinking ? (
          <path d="M53 72 H62" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        ) : (
          <path d="M46 70 Q54 77 62 70" fill="none" stroke={INK} strokeWidth="4" strokeLinecap="round" />
        )}

        {thinking &&
          [
            [96, 46, 2.5],
            [105, 41, 3.3],
            [114, 36, 4.1],
          ].map(([cx, cy, r], i) => (
            <circle
              key={cx}
              cx={cx}
              cy={cy}
              r={r}
              className="origin-center fill-text [transform-box:fill-box] motion-safe:animate-sukat-dot"
              style={{ animationDelay: `${i * 180}ms` }}
            />
          ))}
      </g>
    </svg>
  );
}
