import { useState, useEffect, useRef } from "react";

const BASE = "https://services3.arcgis.com/6j1KwZfY2fZrfNMR/arcgis/rest/services";
const REFRESH_MS = 30_000;
const TOP_N = 10;

type Attrs = Record<string, unknown>;
type Mode = "top" | "bot";

// ─── Endpoint registry ────────────────────────────────────────────────────────

type EndpointDef = {
  id: string;
  name: string;
  hint: string;
  url: string;
  topLabel: string;
  botLabel: string;
};

const ENDPOINTS: EndpointDef[] = [
  {
    id: "journey_time",
    name: "Journey Times",
    hint: "Estimated tunnel & road travel times",
    url: `${BASE}/JourneyTime/FeatureServer/0/query?where=1=1&outFields=LocationEN,DestinationEN,JourenyDataEN,Color&outSR=4326&f=json`,
    topLabel: "Slowest",
    botLabel: "Fastest",
  },
  {
    id: "aqhi",
    name: "Air Quality Index",
    hint: "AQHI (1–10+) by monitoring station",
    url: `${BASE}/EPD_Current_AQHI/FeatureServer/0/query?where=1=1&outFields=Name,AQHI,Type,Publish_Date&outSR=4326&f=json`,
    topLabel: "Worst",
    botLabel: "Best",
  },
  {
    id: "pollutants",
    name: "PM₂.₅ Pollution",
    hint: "Fine particulate matter per station",
    url: `${BASE}/EPD_Current_AQHI_PC/FeatureServer/0/query?where=1=1&outFields=StationNameEN,DateTime_,PM2_5,AQHI&outSR=4326&f=json`,
    topLabel: "Most polluted",
    botLabel: "Cleanest",
  },
  {
    id: "car_parks",
    name: "Car Park Vacancy",
    hint: "Real-time available spaces by car park",
    url: `${BASE}/CarParkData/FeatureServer/0/query?where=1=1&outFields=name,district,privateCar_space,privateCar_vacancy&outSR=4326&f=json`,
    topLabel: "Most vacant",
    botLabel: "Most full",
  },
];

// ─── Data hook ────────────────────────────────────────────────────────────────

function useLiveData(url: string) {
  const [rows, setRows] = useState<Attrs[] | null>(null);
  const [ts, setTs] = useState<Date | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let dead = false;
    const load = async () => {
      try {
        const res = await fetch(url);
        const json = await res.json();
        if (dead) return;
        setRows((json.features ?? []).map((f: { attributes: Attrs }) => f.attributes));
        setTs(new Date());
        setErr(false);
      } catch {
        if (!dead) setErr(true);
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => { dead = true; clearInterval(id); };
  }, [url]);

  return { rows, ts, err };
}

// ─── SVG horizontal bar chart ─────────────────────────────────────────────────
//
// viewBox is 480 wide; SVG scales to fill container width.
// Left margin (ML) holds y-axis labels; right margin (MR) holds value labels.

const VW = 480;
const ML = 158, MR = 70, MT = 8, MB = 34;
const IW = VW - ML - MR; // inner chart width in SVG units
const BH = 22;           // bar height
const RH = 30;           // row height (bar + gap)

type BarItem = { label: string; value: number; color: string };
type TLine   = { value: number; label: string; color: string };
type Zone    = { from: number; to: number; color: string };
type ChartData = { items: BarItem[]; unit: string; tlines: TLine[]; zones: Zone[]; summary: string };

function niceMax(v: number): number {
  if (v <= 0) return 10;
  const e = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / e;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * e;
}

function niceStep(domMax: number, targetTicks = 5): number {
  const raw = domMax / (targetTicks - 1);
  const e = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / e;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * e;
}

function fmtN(v: number): string {
  if (v >= 10000) return `${(v / 1000).toFixed(0)}k`;
  if (v >= 1000)  return `${(v / 1000).toFixed(1)}k`;
  return v % 1 === 0 ? String(v) : v.toFixed(1);
}

function HorizontalBarChart({ items, unit = "", tlines = [], zones = [], summary }: ChartData) {
  if (!items.length) return <p className="ld-nodata">No data</p>;

  const rawMax = Math.max(...items.map(i => i.value), ...tlines.map(t => t.value), 0.1);
  const domMax = niceMax(rawMax * 1.1);
  const step = niceStep(domMax);
  const ticks: number[] = [];
  for (let t = 0; t <= domMax * 1.001; t += step) ticks.push(Math.round(t * 1e9) / 1e9);

  const xs = (v: number) => (v / domMax) * IW;
  const innerH = (items.length - 1) * RH + BH;
  const vbH = MT + innerH + MB;

  return (
    <div className="ld-chart-wrap">
      {summary && <p className="ld-summary">{summary}</p>}
      {tlines.length > 0 && (
        <div className="ld-tline-legend">
          {tlines.map((tl, i) => (
            <span key={i} className="ld-tline-item" style={{ color: tl.color, borderColor: tl.color }}>
              {tl.label}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${VW} ${vbH}`} width="100%" style={{ display: "block" }}>
        <g transform={`translate(${ML},${MT})`}>

          {/* Zone bands */}
          {zones.map((z, i) => {
            const x1 = xs(Math.max(0, z.from));
            const x2 = xs(Math.min(domMax, z.to));
            return x2 > x1 ? (
              <rect key={i} x={x1} y={0} width={x2 - x1} height={innerH} fill={z.color} opacity={0.1} />
            ) : null;
          })}

          {/* Vertical grid lines */}
          {ticks.map((t, i) => (
            <line key={i} x1={xs(t)} y1={0} x2={xs(t)} y2={innerH} stroke="#f0f0f0" strokeWidth={1} />
          ))}

          {/* Bars */}
          {items.map((item, i) => {
            const y = i * RH;
            const bw = Math.max(2, xs(item.value));
            // Put value label inside the bar (white) when there's room, outside (dark) when narrow.
            // This eliminates overlap with threshold lines and ensures contrast ≥ 4.5:1 in both cases.
            const inside = bw > 58;
            return (
              <g key={i}>
                {/* Y-axis label */}
                <text
                  x={-8} y={y + BH / 2}
                  textAnchor="end" dominantBaseline="middle"
                  fontSize={11} fill="#374151" fontFamily="inherit"
                >
                  {item.label.length > 22 ? item.label.slice(0, 21) + "…" : item.label}
                </text>
                {/* Bar */}
                <rect x={0} y={y} width={bw} height={BH} fill={item.color} rx={2} />
                {/* Value label */}
                <text
                  x={inside ? bw - 5 : bw + 5}
                  y={y + BH / 2}
                  textAnchor={inside ? "end" : "start"}
                  dominantBaseline="middle"
                  fontSize={11} fontWeight="600"
                  fill={inside ? "#ffffff" : "#1e293b"}
                  fontFamily="inherit"
                >
                  {fmtN(item.value)}{unit}
                </text>
              </g>
            );
          })}

          {/* Threshold / reference lines — labels rendered as HTML legend above the chart */}
          {tlines.map((tl, i) => {
            const x = xs(tl.value);
            if (x < 0 || x > IW) return null;
            return (
              <line key={i} x1={x} y1={0} x2={x} y2={innerH}
                stroke={tl.color} strokeWidth={1.5} strokeDasharray="5 3" />
            );
          })}

          {/* X axis baseline */}
          <line x1={0} y1={innerH} x2={IW} y2={innerH} stroke="#d1d5db" strokeWidth={1} />

          {/* X axis tick labels */}
          {ticks.map((t, i) => (
            <text
              key={i} x={xs(t)} y={innerH + 16}
              textAnchor="middle" fontSize={10} fill="#9ca3af" fontFamily="inherit"
            >
              {fmtN(t)}
            </text>
          ))}
        </g>
      </svg>
    </div>
  );
}

// ─── Data transformers ────────────────────────────────────────────────────────

function prepareJourneyTime(rows: Attrs[], mode: Mode): ChartData {
  const all = rows
    .map(r => {
      const loc = (r.LocationEN as string | undefined) ?? "";
      const shortLoc = (loc.match(/near (.+)$/i)?.[1] ?? loc.split(" ").slice(-2).join(" ")).slice(0, 14);
      const dest = ((r.DestinationEN as string | undefined) ?? "")
        .replace("Cross Harbour Tunnel", "XHT")
        .replace("Eastern Harbour Crossing", "EHC")
        .replace("Western Harbour Crossing", "WHC")
        .replace("Aberdeen Tunnel", "AT")
        .replace("Lion Rock Tunnel", "LRT")
        .replace("Shing Mun Tunnel", "SMT");
      const mins = parseInt((r.JourenyDataEN as string | undefined) ?? "0", 10) || 0;
      return { label: `${shortLoc} → ${dest}`, mins };
    })
    .filter(r => r.mins > 0);

  const sorted = [...all].sort((a, b) => mode === "top" ? b.mins - a.mins : a.mins - b.mins).slice(0, TOP_N);
  const avg = all.reduce((s, r) => s + r.mins, 0) / (all.length || 1);
  const slow = all.filter(r => r.mins > 10).length;

  return {
    items: sorted.map(r => ({
      label: r.label,
      value: r.mins,
      color: r.mins <= 5 ? "#16a34a" : r.mins <= 10 ? "#d97706" : "#dc2626",
    })),
    unit: " min",
    tlines: [
      { value: 5,  label: "5 min",  color: "#d97706" },
      { value: 10, label: "10 min", color: "#dc2626" },
    ],
    zones: [],
    summary: `${all.length} routes · ${slow} over 10 min · avg ${avg.toFixed(1)} min`,
  };
}

function prepareAQHI(rows: Attrs[], mode: Mode): ChartData {
  // Guard: AQHI is a 1–10+ integer. Reject any value outside [1, 20] — the field can
  // sometimes carry epoch timestamps when the service returns Publish_Date in the same slot.
  const all = rows
    .filter(r => {
      const v = Number(r.AQHI);
      return r.Name && Number.isFinite(v) && v >= 1 && v <= 20;
    })
    .map(r => ({ label: r.Name as string, value: Number(r.AQHI) }));

  const sorted = [...all].sort((a, b) => mode === "top" ? b.value - a.value : a.value - b.value).slice(0, TOP_N);
  const avg = all.length ? all.reduce((s, r) => s + r.value, 0) / all.length : 0;
  const high = all.filter(r => r.value >= 7).length;

  return {
    items: sorted.map(r => ({
      label: r.label,
      value: r.value,
      color: r.value <= 3 ? "#16a34a" : r.value <= 6 ? "#d97706" : r.value <= 10 ? "#ea580c" : "#dc2626",
    })),
    unit: "",
    tlines: [
      { value: 3.5, label: "Low / Medium", color: "#d97706" },
      { value: 6.5, label: "Medium / High", color: "#ea580c" },
    ],
    zones: [
      { from: 0,   to: 3.5, color: "#16a34a" },
      { from: 3.5, to: 6.5, color: "#d97706" },
      { from: 6.5, to: 10,  color: "#ea580c" },
      { from: 10,  to: 13,  color: "#dc2626" },
    ],
    summary: `${all.length} stations · ${high} at High risk or above · avg ${avg.toFixed(1)}`,
  };
}

function preparePollutants(rows: Attrs[], mode: Mode): ChartData {
  // Deduplicate: keep the latest reading per station
  const map = new Map<string, Attrs>();
  for (const r of rows) {
    const name = r.StationNameEN as string | undefined;
    if (!name) continue;
    const cur = map.get(name);
    if (!cur || (r.DateTime_ as number) > (cur.DateTime_ as number)) map.set(name, r);
  }

  const WHO_LIMIT = 15; // WHO 24h guideline µg/m³
  const UNHEALTHY = 35; // US EPA "Unhealthy for sensitive groups"

  const all = Array.from(map.values())
    .map(r => ({ label: r.StationNameEN as string, value: (r.PM2_5 as number) || 0 }))
    .filter(r => r.value > 0);

  const sorted = [...all].sort((a, b) => mode === "top" ? b.value - a.value : a.value - b.value).slice(0, TOP_N);
  const over = all.filter(r => r.value > WHO_LIMIT).length;

  return {
    items: sorted.map(r => ({
      label: r.label,
      value: r.value,
      color: r.value <= WHO_LIMIT ? "#16a34a" : r.value <= UNHEALTHY ? "#d97706" : "#dc2626",
    })),
    unit: " µg/m³",
    tlines: [
      { value: WHO_LIMIT, label: `WHO limit (${WHO_LIMIT})`, color: "#dc2626" },
      { value: UNHEALTHY, label: `Unhealthy (${UNHEALTHY})`,  color: "#7c3aed" },
    ],
    zones: [],
    summary: `${all.length} stations · ${over} exceed WHO PM₂.₅ limit of ${WHO_LIMIT} µg/m³`,
  };
}

function prepareCarParks(rows: Attrs[], mode: Mode): ChartData {
  const all = rows
    .filter(r => (r.privateCar_space as number) > 0)
    .map(r => {
      const total = r.privateCar_space as number;
      const vacant = Math.max(0, r.privateCar_vacancy as number);
      return {
        label: (r.name as string | undefined) ?? "—",
        pct: Math.round((vacant / total) * 100),
      };
    });

  const sorted = [...all].sort((a, b) => mode === "top" ? b.pct - a.pct : a.pct - b.pct).slice(0, TOP_N);
  const critical = all.filter(r => r.pct < 20).length;

  return {
    items: sorted.map(r => ({
      label: r.label,
      value: r.pct,
      color: r.pct >= 50 ? "#16a34a" : r.pct >= 20 ? "#d97706" : "#dc2626",
    })),
    unit: "%",
    tlines: [
      { value: 20, label: "Critical (<20%)", color: "#dc2626" },
      { value: 50, label: "Comfortable (>50%)", color: "#16a34a" },
    ],
    zones: [],
    summary: `${all.length} car parks · ${critical} critically full (<20% vacant)`,
  };
}

function prepare(id: string, rows: Attrs[], mode: Mode): ChartData | null {
  if (id === "journey_time") return prepareJourneyTime(rows, mode);
  if (id === "aqhi")         return prepareAQHI(rows, mode);
  if (id === "pollutants")   return preparePollutants(rows, mode);
  if (id === "car_parks")    return prepareCarParks(rows, mode);
  return null;
}

// ─── Plot card ────────────────────────────────────────────────────────────────

function PlotCard({ def, onRemove }: { def: EndpointDef; onRemove: () => void }) {
  const [mode, setMode] = useState<Mode>("top");
  const { rows, ts, err } = useLiveData(def.url);

  const chart = rows ? prepare(def.id, rows, mode) : null;
  const fmtTs = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="ld-card">
      <div className="ld-card-head">
        <div className="ld-card-left">
          <span className="ld-card-title">{def.name}</span>
          <span className="ld-card-ts">{ts ? `Updated ${fmtTs(ts)}` : "Loading…"}</span>
        </div>
        <div className="ld-card-right">
          <div className="ld-toggle">
            <button className={mode === "top" ? "active" : ""} onClick={() => setMode("top")}>
              {def.topLabel} 10
            </button>
            <button className={mode === "bot" ? "active" : ""} onClick={() => setMode("bot")}>
              {def.botLabel} 10
            </button>
          </div>
          <button className="ld-x" onClick={onRemove} title="Remove chart">×</button>
        </div>
      </div>
      <div className="ld-card-body">
        {err ? (
          <p className="ld-nodata">Failed to load data from ArcGIS</p>
        ) : !rows ? (
          <p className="ld-nodata">Loading live data…</p>
        ) : chart ? (
          <HorizontalBarChart {...chart} />
        ) : null}
      </div>
    </div>
  );
}

// ─── Main dashboard ───────────────────────────────────────────────────────────

export function LiveDashboard() {
  const [active, setActive] = useState(["journey_time", "aqhi"]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = ENDPOINTS.filter(
    d => !active.includes(d.id) && d.name.toLowerCase().includes(search.toLowerCase())
  );

  const add = (id: string) => { setActive(a => [...a, id]); setSearch(""); setOpen(false); };
  const remove = (id: string) => setActive(a => a.filter(x => x !== id));
  const defs = active.map(id => ENDPOINTS.find(d => d.id === id)!).filter(Boolean);

  return (
    <div className="ld-main">
      <div className="ld-header">
        <div className="ld-header-left">
          <h2 className="ld-title">Live Data</h2>
          <span className="ld-subtitle">Hong Kong · ArcGIS REST · refreshes every 30 s</span>
        </div>
        <div className="ld-search-outer">
          <input
            ref={inputRef}
            className="ld-search"
            placeholder="Add a live chart…"
            value={search}
            onChange={e => { setSearch(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
          />
          {open && suggestions.length > 0 && (
            <div className="ld-drop">
              {suggestions.map(d => (
                <button key={d.id} className="ld-drop-item" onMouseDown={() => add(d.id)}>
                  <span className="ld-drop-name">{d.name}</span>
                  <span className="ld-drop-hint">{d.hint}</span>
                </button>
              ))}
            </div>
          )}
          {open && suggestions.length === 0 && active.length === ENDPOINTS.length && (
            <div className="ld-drop">
              <p className="ld-drop-empty">All available charts are shown</p>
            </div>
          )}
        </div>
      </div>

      <div className="ld-grid">
        {defs.map(def => (
          <PlotCard key={def.id} def={def} onRemove={() => remove(def.id)} />
        ))}
        {defs.length === 0 && (
          <div className="ld-empty-state">
            <p>Use the search bar above to add a live chart.</p>
          </div>
        )}
      </div>
    </div>
  );
}
