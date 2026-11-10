import { formatRange } from "@/lib/dates";
import type { ChatData } from "@/lib/types";

/**
 * The table or bar chart under an answer. Every number here comes from the server's
 * tool result, not from the AI's text.
 */
export function ChatDataView({ data }: { data: ChatData }) {
  return (
    <figure className="mt-4">
      <figcaption className="mb-2 text-[13px] font-bold text-text">{data.title}</figcaption>
      {data.kind === "bar" ? <Bars data={data} /> : <Table data={data} />}
    </figure>
  );
}

/** "Based on sales from 2–6 November" (nothing when the data has no date range). */
export function basisLine(data: ChatData): string | null {
  if (!data.range || !data.basis) return null;
  const what = data.basis === "sales" ? "sales" : "stock changes";
  return `Based on ${what} from ${formatRange(data.range.start, data.range.end)}`;
}

/**
 * Horizontal bars on one baseline, one hue (dark stone, as in the design). For a sales
 * comparison the earlier period is lighter, so "now" stands out. Each row: the name and
 * value as text (text colors) on one line, the bar under it, so long names fit a phone.
 */
function Bars({ data }: { data: ChatData }) {
  const values = data.bars.map((b) => Number(b.value));
  const max = Math.max(0, ...values);
  const comparison = data.tool === "sales_summary";
  return (
    <ul className="flex flex-col gap-2.5">
      {data.bars.map((b, i) => {
        const pct = max > 0 ? (values[i] / max) * 100 : 0;
        const muted = comparison && i < data.bars.length - 1;
        return (
          <li key={`${b.label}-${i}`} className="text-[13px]">
            <span className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate text-muted" title={b.label}>
                {b.label}
              </span>
              <strong className="font-semibold whitespace-nowrap text-text">{b.display}</strong>
            </span>
            <span className="mt-1 block h-[9px] overflow-hidden rounded bg-border" aria-hidden>
              <span
                className={`block h-full rounded-r ${muted ? "bg-bar-muted" : "bg-bar"}`}
                style={{ width: `${pct}%` }}
              />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Table({ data }: { data: ChatData }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className="w-full border-collapse text-left text-[13px]">
        <thead>
          <tr className="border-b border-border text-subtle">
            {data.columns.map((c) => (
              <th key={c} scope="col" className="py-1.5 pr-3 font-semibold whitespace-nowrap last:pr-0">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-b-0">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`py-1.5 pr-3 align-top last:pr-0 ${j === 0 ? "text-text" : "whitespace-nowrap text-muted"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
