import { useEffect, useState } from "react";
import { api } from "../api";
import type { Development } from "../types";

export function Feed({ worldId, curtain, refreshKey }: {
  worldId: number; curtain: boolean; refreshKey: number;
}) {
  const [devs, setDevs] = useState<Development[]>([]);
  useEffect(() => { api.developments(worldId, curtain).then(setDevs); },
    [worldId, curtain, refreshKey]);

  if (devs.length === 0) {
    return <div className="empty">No developments yet.<br />Advance time, or reach in.</div>;
  }
  return (
    <div className="pane">
      {devs.map((d) => (
        <div className="dev" key={d.id}>
          <div className="head">
            <span className={`tier ${d.tier}`}>{d.tier}</span>
            <span className="hl">{d.headline}</span>
          </div>
          {d.body && <div className="body">{d.body}</div>}
          <div className="meta">
            Day {d.day}{d.agent ? ` · ${d.agent}` : ""} · {d.source}
            {d.escalate ? " · ⤴ pivot" : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
