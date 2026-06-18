import { useEffect, useState } from "react";
import { api } from "../api";
import type { LedgerView } from "../types";

const COLORS = ["#c9a14a", "#5fae8c", "#c25b5b", "#7d9ad9", "#b07dd9"];

export function Ledgers({ worldId, curtain, refreshKey }: {
  worldId: number; curtain: boolean; refreshKey: number;
}) {
  const [data, setData] = useState<{ curtained: boolean; ledgers: LedgerView[] }>(
    { curtained: true, ledgers: [] });
  useEffect(() => { api.ledgers(worldId, curtain).then(setData); },
    [worldId, curtain, refreshKey]);

  if (!curtain) {
    return <div className="empty">🔴 Contested-control ledgers are GM-only.<br />
      Flip the curtain to see where pressure is building.</div>;
  }
  if (data.ledgers.length === 0) {
    return <div className="empty">No contested ledgers yet.<br />
      They open when two agents reach for the same thing.</div>;
  }

  return (
    <div className="pane">
      {data.ledgers.map((l) => {
        const claimants = Object.entries(l.control).filter(([k]) => k !== "_neutral");
        const neutral = l.control["_neutral"] || 0;
        return (
          <div className="ledger" key={l.entity}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <b>{l.entity}</b>
              <span className="phase">{l.phase}</span>
            </div>
            <div className="bar">
              {claimants.map(([name, pts], i) => (
                <span key={name} title={`${name} ${pts}`}
                  style={{ width: `${(pts / l.total) * 100}%`, background: COLORS[i % COLORS.length] }} />
              ))}
              <span style={{ width: `${(neutral / l.total) * 100}%`, background: "#2a2e3a" }} />
            </div>
            <div className="faint" style={{ fontSize: 11, marginTop: 3 }}>
              holder: {l.holder || "contested"} · {l.standing}
            </div>
          </div>
        );
      })}
    </div>
  );
}
