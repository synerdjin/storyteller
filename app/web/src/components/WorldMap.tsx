import type { MapData } from "../types";

const SALIENCE_COLOR = ["#5a6072", "#6b7a8a", "#7d9a86", "#c9a14a", "#d98a4a", "#c25b5b"];

export function WorldMap({
  data, selected, onSelect,
}: {
  data: MapData;
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const W = 1000;
  const H = 700;
  const locById = new Map(data.locations.map((l) => [l.id, l]));

  // fan agents out around their location so co-located tokens don't overlap
  const byLoc = new Map<number | string, typeof data.agents>();
  for (const a of data.agents) {
    const key = a.location_id ?? "none";
    if (!byLoc.has(key)) byLoc.set(key, []);
    byLoc.get(key)!.push(a);
  }
  const placed = data.agents.map((a) => {
    const loc = a.location_id != null ? locById.get(a.location_id) : undefined;
    const peers = byLoc.get(a.location_id ?? "none")!;
    const i = peers.indexOf(a);
    const n = peers.length;
    const cx = (loc?.x ?? 0.5) * W;
    const cy = (loc?.y ?? 0.5) * H;
    const r = n > 1 ? 46 : 0;
    const ang = (i / Math.max(1, n)) * Math.PI * 2;
    return { a, x: cx + Math.cos(ang) * r, y: cy + Math.sin(ang) * r + (n > 1 ? 0 : 34) };
  });

  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
      {data.locations.map((l) => (
        <g key={l.id}>
          <circle className="loc-node" cx={l.x * W} cy={l.y * H} r={64} />
          <text className="loc-label" x={l.x * W} y={l.y * H - 74}>{l.name}</text>
        </g>
      ))}
      {placed.map(({ a, x, y }) => (
        <g
          key={a.id}
          className={`token ${a.living ? "" : "dead"} ${selected === a.id ? "sel" : ""}`}
          onClick={() => onSelect(a.id)}
        >
          <circle cx={x} cy={y} r={a.kind === "faction" ? 16 : 12}
            fill={SALIENCE_COLOR[Math.min(5, a.salience)] || "#6b7a8a"} />
          <text x={x} y={y + 26}>{a.display_name}</text>
        </g>
      ))}
    </svg>
  );
}
