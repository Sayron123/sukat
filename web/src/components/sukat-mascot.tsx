import { useId } from "react";

import { Glow } from "./mascot";

import "./sukat-mascot.css";

export type Motion = "idle" | "walk" | "wave" | "thinking" | "happy" | "confused" | "measure";

const CLASS: Record<Motion, string> = {
  idle: "idle",
  walk: "walk",
  wave: "wave",
  thinking: "think",
  happy: "happy",
  confused: "confused",
  measure: "measure",
};

const ALT: Record<Motion, string> = {
  idle: "Sukat mascot",
  walk: "Sukat mascot, walking",
  wave: "Sukat mascot, waving",
  thinking: "Sukat mascot, thinking",
  happy: "Sukat mascot, happy",
  confused: "Sukat mascot, confused",
  measure: "Sukat mascot, measuring",
};

const INK = "#1C1917";
const SPARKS = [
  { x: 8, y: 6, scale: 1 },
  { x: 104, y: 0, scale: 0.8 },
  { x: 116, y: 22, scale: 0.55 },
];
const DOTS = [
  { cx: 104, cy: 14, r: 3 },
  { cx: 113, cy: 8, r: 4 },
  { cx: 122, cy: 2, r: 5 },
];

function label(alt: string) {
  return alt ? { role: "img", "aria-label": alt } : { "aria-hidden": true };
}

export function SukatMascot({
  motion = "idle",
  size = 120,
  glow = false,
  alt,
  className = "",
}: {
  motion?: Motion;
  size?: number;
  glow?: boolean;
  alt?: string;
  className?: string;
}) {
  const id = useId();
  const wide = motion === "measure";
  const width = wide ? 214 : 148;
  const crop = motion === "walk" ? "overflow-hidden" : "overflow-visible";

  const svg = (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`-14 -24 ${width} 140`}
      width={Math.round((size * width) / 148)}
      height={Math.round((size * 140) / 148)}
      {...label(alt ?? ALT[motion])}
      className={`sukat-mo ${CLASS[motion]} relative shrink-0 ${crop} ${glow ? "" : className}`}
    >
      <Defs id={id} />
      {motion === "walk" && (
        <>
          <rect x="-14" y="109" width="148" height="12" className="fill-[#E7E5E4] dark:fill-border" />
          <g className="ruler">
            <path d="M-40 109 H200" stroke="#78716C" strokeWidth="7" strokeDasharray="1.4 8.6" />
            <path d="M-40 109 H200" stroke="#C2410C" strokeWidth="12" strokeDasharray="2 18" />
          </g>
        </>
      )}
      <ellipse className="shadow" cx="54" cy="109" rx="38" ry="5.5" fill="#000" fillOpacity="0.16" />
      <g className="mascot">
        <g className="hop">
          <g className="feet">
            <g className="footL">
              <rect x="27" y="94" width="20" height="14" rx="6" fill="#292524" />
              <rect x="31" y="101" width="9" height="3" rx="1.5" fill="#57534E" />
            </g>
            <g className="footR">
              <rect x="61" y="94" width="20" height="14" rx="6" fill="#292524" />
              <rect x="65" y="101" width="9" height="3" rx="1.5" fill="#57534E" />
            </g>
          </g>
          <Body id={id} motion={motion} tail={wide ? 10 : 80} tip={wide ? 98 : 112} />
        </g>
      </g>
      {motion === "thinking" &&
        DOTS.map((dot, i) => <circle key={dot.cx} className={`d${i + 1} fill-text`} {...dot} />)}
      {motion === "happy" &&
        SPARKS.map((s) => (
          <g key={s.x} className="spark">
            <path
              transform={`translate(${s.x} ${s.y}) scale(${s.scale})`}
              d="M0 -9 Q1.5 -1.5 9 0 Q1.5 1.5 0 9 Q-1.5 1.5 -9 0 Q-1.5 -1.5 0 -9 Z"
              fill="#C2410C"
              stroke={INK}
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
          </g>
        ))}
      {motion === "confused" && (
        <g className="q">
          <text
            x="10"
            y="28"
            fontFamily="Arial Black, Arial, sans-serif"
            fontWeight="900"
            fontSize="30"
            fill="#C2410C"
            stroke={INK}
            strokeWidth="2.5"
            paintOrder="stroke"
            textAnchor="middle"
          >
            ?
          </text>
        </g>
      )}
      {motion === "measure" && (
        <g className="read">
          <rect x="128" y="18" width="54" height="24" rx="12" className="fill-text" />
          <text
            x="155"
            y="35"
            fontFamily="Inter, Arial, sans-serif"
            fontSize="13"
            fontWeight="800"
            textAnchor="middle"
            className="fill-inverse"
          >
            1.2 m
          </text>
        </g>
      )}
    </svg>
  );

  if (!glow) return svg;
  return (
    <span className={`relative inline-grid shrink-0 place-items-center ${className}`}>
      <Glow />
      {svg}
    </span>
  );
}

export function SukatLogo({ height = 32, alt = "Sukat", className = "" }: { height?: number; alt?: string; className?: string }) {
  const id = useId();
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="4 12 246 96"
      width={Math.round((height * 246) / 96)}
      height={height}
      {...label(alt)}
      className={`shrink-0 overflow-visible ${className}`}
    >
      <Defs id={id} />
      <g className="mascot">
        <g className="hop">
          <Body id={id} motion="idle" tail={80} tip={236} />
        </g>
      </g>
      <text x="104" y="48" fontWeight="800" fontSize="46" letterSpacing="-1" className="fill-text font-brand">
        Sukat
      </text>
    </svg>
  );
}

function Defs({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}c`} x1="0" y1="0" x2="0.3" y2="1">
        <stop offset="0" stopColor="#F97316" />
        <stop offset="0.55" stopColor="#C2410C" />
        <stop offset="1" stopColor="#9A3412" />
      </linearGradient>
      <radialGradient id={`${id}f`} cx="0.38" cy="0.32" r="0.8">
        <stop offset="0" stopColor="#FFFFFF" />
        <stop offset="0.75" stopColor="#F5F5F4" />
        <stop offset="1" stopColor="#D6D3D1" />
      </radialGradient>
      <linearGradient id={`${id}m`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#E7E5E4" />
        <stop offset="1" stopColor="#A8A29E" />
      </linearGradient>
      <clipPath id={`${id}k`}>
        <rect x="18" y="26" width="72" height="68" rx="20" />
      </clipPath>
    </defs>
  );
}

function Body({ id, motion, tail, tip }: { id: string; motion: Motion; tail: number; tip: number }) {
  const blade = `M${tail} 60 H${tip}`;
  return (
    <g className="body">
      <rect x="9" y="36" width="14" height="44" rx="6" fill="#44403C" />
      <rect x="13" y="42" width="4" height="30" rx="2" fill="#57534E" />
      <rect x="58" y="17" width="24" height="15" rx="6" fill="#292524" />
      {[64, 69, 74].map((x) => (
        <path key={x} d={`M${x} 21 V27`} stroke="#78716C" strokeWidth="2" strokeLinecap="round" />
      ))}
      <g className="blade">
        <g className="bladeSlide">
          <path d={blade} fill="none" stroke="#78716C" strokeWidth="16" />
          <path d={blade} fill="none" stroke="#F5F5F4" strokeWidth="10" />
          <path d={blade} fill="none" stroke="#57534E" strokeWidth="5" strokeDasharray="1.3 3.7" />
          <path d={blade} fill="none" stroke="#C2410C" strokeWidth="10" strokeDasharray="2 18" strokeDashoffset="-8" />
          <g transform={`translate(${tip} 60)`}>
            <path
              d="M-6 -8 H3 V14 H-2 V-8 Z"
              fill={`url(#${id}m)`}
              stroke="#57534E"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <circle cx="-7" cy="-3" r="1.6" fill="#57534E" />
            <circle cx="-7" cy="3" r="1.6" fill="#57534E" />
          </g>
        </g>
      </g>
      <rect x="18" y="32" width="72" height="68" rx="20" fill="#7C2D12" />
      <rect x="18" y="26" width="72" height="68" rx="20" fill={`url(#${id}c)`} />
      <g clipPath={`url(#${id}k)`}>
        <path d="M18 84 H90 V100 H18 Z" fill="#7C2D12" />
      </g>
      <rect x="18" y="26" width="72" height="68" rx="20" fill="none" stroke="#7C2D12" strokeWidth="2" />
      <rect x="80" y="53" width="12" height="14" rx="3" fill={INK} />
      <path
        d="M28 38 Q31 31 40 30"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.5"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <circle cx="52" cy="55" r="25" fill="#E7E5E4" stroke="#7C2D12" strokeWidth="2.5" />
      <circle cx="52" cy="55" r="22.3" fill="none" stroke="#78716C" strokeWidth="2.2" strokeDasharray="0.9 4.9" />
      <circle cx="52" cy="55" r="19" fill={`url(#${id}f)`} stroke="#D6D3D1" strokeWidth="1.5" />
      <Face motion={motion} />
    </g>
  );
}

function Face({ motion }: { motion: Motion }) {
  const line = { fill: "none", stroke: INK, strokeWidth: 3.5, strokeLinecap: "round" } as const;

  if (motion === "thinking") {
    return (
      <g className="face">
        <g className="eyes" fill={INK}>
          <circle cx="45" cy="52" r="4" />
          <circle cx="65" cy="52" r="4" />
        </g>
        <g className="mouth">
          <path d="M51 65 H60" {...line} />
        </g>
      </g>
    );
  }

  if (motion === "happy") {
    return (
      <g className="face">
        <g className="eyes" fill={INK}>
          <path d="M38 56 Q42 49 46 56 M58 56 Q62 49 66 56" {...line} />
        </g>
        <g className="mouth">
          <path d="M44 62 Q52 74 60 62 Z" fill={INK} stroke={INK} strokeWidth="2" strokeLinejoin="round" />
        </g>
      </g>
    );
  }

  if (motion === "confused") {
    return (
      <g className="face">
        <g className="eyes" fill={INK}>
          <circle cx="42" cy="55" r="4" />
          <circle cx="62" cy="54" r="4" />
          <path d="M57 45 L67 48" {...line} />
        </g>
        <g className="mouth">
          <path d="M44 66 q4 -5 8 0 t8 0" {...line} />
        </g>
      </g>
    );
  }

  const shift = motion === "measure" ? 2 : 0;
  return (
    <g className="face">
      <g className="eyes" fill={INK}>
        <circle cx={42 + shift} cy="54" r="4" />
        <circle cx={62 + shift} cy="54" r="4" />
      </g>
      <g className="mouth">
        <path d={motion === "measure" ? "M50 65 Q56 69 62 65" : "M45 63 Q52 69 59 63"} {...line} />
      </g>
    </g>
  );
}
