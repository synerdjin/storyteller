import { useCallback, useEffect, useState } from "react";
import { api, tickStream } from "./api";
import type { MapData, WorldSnapshot, WorldSummary } from "./types";
import { WorldMap } from "./components/WorldMap";
import { Inspector } from "./components/Inspector";
import { Feed } from "./components/Feed";
import { Ledgers } from "./components/Ledgers";
import { GodHand } from "./components/GodHand";
import { Wizard } from "./components/Wizard";

type Tab = "inspect" | "world" | "pressure" | "god";

export function App() {
  const [worlds, setWorlds] = useState<WorldSummary[]>([]);
  const [worldId, setWorldId] = useState<number | null>(null);
  const [snap, setSnap] = useState<WorldSnapshot | null>(null);
  const [map, setMap] = useState<MapData | null>(null);
  const [curtain, setCurtain] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("world");
  const [refreshKey, setRefreshKey] = useState(0);
  const [directors, setDirectors] = useState(false);
  const [wizard, setWizard] = useState(false);
  const [elapsed, setElapsed] = useState(1);
  const [dawdle, setDawdle] = useState(false);
  const [fail, setFail] = useState(false);
  const [ticking, setTicking] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    api.status().then((s) => setDirectors(s.directors_available));
    refreshWorlds();
  }, []);

  const refreshWorlds = async () => {
    const ws = await api.listWorlds();
    setWorlds(ws);
    if (ws.length && worldId == null) selectWorld(ws[0].id);
  };

  const selectWorld = (id: number) => {
    setWorldId(id);
    setSelected(null);
    setTab("world");
  };

  const reload = useCallback(async () => {
    if (worldId == null) return;
    const [s, m] = await Promise.all([api.world(worldId, curtain), api.map(worldId)]);
    setSnap(s);
    setMap(m);
  }, [worldId, curtain]);

  useEffect(() => { reload(); }, [reload, refreshKey]);

  const advance = async () => {
    if (worldId == null) return;
    setTicking(true);
    setLog([]);
    const add = (s: string) => setLog((l) => [...l, s]);
    try {
      await tickStream(worldId, { elapsed, dawdle, fail, run_directors: true }, (ev, data) => {
        if (ev === "deterministic") {
          add(`tick: ${data.moved} moved, ${data.interactions.length} collision(s), ` +
            `${data.developments.length} templated → Day ${data.new_day}`);
        } else if (ev === "directors_unavailable") {
          add("directors unavailable (no API key) — collisions detected but not narrated");
        } else if (ev === "director_start") {
          add(`director: resolving ${data.collisions} collision(s), ${data.reflection} reflection(s)…`);
        } else if (ev === "director_done") {
          if (data.lite) add(`✓ Sonnet: ${data.lite.summary}`);
          if (data.opus) add(`✓ Opus pivot: ${data.opus.summary}`);
        } else if (ev === "error") {
          add(`error: ${data.message}`);
        }
      });
    } catch (e) {
      add("error: " + (e as Error).message);
    }
    setTicking(false);
    bump();
  };

  const onSelectAgent = (id: number) => { setSelected(id); setTab("inspect"); };

  return (
    <div className="app">
      <div className="topbar">
        <h1>🐜 ANT FARM</h1>
        <select value={worldId ?? ""} onChange={(e) => selectWorld(+e.target.value)}>
          {worlds.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          {worlds.length === 0 && <option value="">— no worlds —</option>}
        </select>
        <button onClick={() => setWizard(true)}>+ New world</button>
        {snap && <span className="day">Day {snap.current_day}</span>}
        {snap && <span className="muted">{snap.game.toUpperCase()} · {snap.play_mode}</span>}
        <span className="grow" />
        <span className="faint" style={{ fontSize: 12 }}>
          directors: {directors ? "ready" : "no key (deterministic only)"}
        </span>
        <div className={`curtain-toggle ${curtain ? "on" : ""}`} onClick={() => setCurtain(!curtain)}>
          <span className="dot" />
          {curtain ? "curtain: lifted" : "curtain: down"}
        </div>
      </div>

      {worldId == null ? (
        <div className="empty" style={{ marginTop: 80 }}>
          No world yet. <button className="primary" onClick={() => setWizard(true)}>Create one →</button>
        </div>
      ) : (
        <div className="layout">
          <div className="stage" style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ flex: 1, position: "relative" }}>
              {map && <WorldMap data={map} selected={selected} onSelect={onSelectAgent} />}
            </div>
            <div className="timebar">
              <button className="primary" disabled={ticking} onClick={advance}>
                {ticking ? "…advancing" : "▶ Advance"}
              </button>
              <label className="chk">skip
                <input type="number" min={1} max={30} value={elapsed} style={{ width: 52 }}
                  onChange={(e) => setElapsed(Math.max(1, +e.target.value))} /> day(s)
              </label>
              <label className="chk"><input type="checkbox" checked={dawdle}
                onChange={(e) => setDawdle(e.target.checked)} /> dawdle</label>
              <label className="chk"><input type="checkbox" checked={fail}
                onChange={(e) => setFail(e.target.checked)} /> fail-forward</label>
              <span className="grow" style={{ flex: 1 }} />
              <span className="faint">{snap?.tone}</span>
              <div className="log">{log.map((l, i) => <div key={i}>· {l}</div>)}</div>
            </div>
          </div>

          <div className="sidebar">
            <div className="tabs">
              <button className={tab === "inspect" ? "active" : ""} onClick={() => setTab("inspect")}>Inspect</button>
              <button className={tab === "world" ? "active" : ""} onClick={() => setTab("world")}>World</button>
              <button className={tab === "pressure" ? "active" : ""} onClick={() => setTab("pressure")}>Pressure</button>
              <button className={tab === "god" ? "active" : ""} onClick={() => setTab("god")}>God-hand</button>
            </div>

            {tab === "inspect" && (selected != null
              ? <Inspector worldId={worldId} agentId={selected} curtain={curtain}
                  directorsAvailable={directors} onChanged={bump} />
              : <div className="empty">Click an ant on the map to read it.</div>)}
            {tab === "world" && <Feed worldId={worldId} curtain={curtain} refreshKey={refreshKey} />}
            {tab === "pressure" && <Ledgers worldId={worldId} curtain={curtain} refreshKey={refreshKey} />}
            {tab === "god" && map &&
              <GodHand worldId={worldId} agents={map.agents} onDone={bump} />}
          </div>
        </div>
      )}

      {wizard && (
        <Wizard directorsAvailable={directors}
          onClose={() => setWizard(false)}
          onCreated={(id) => { setWizard(false); refreshWorlds().then(() => selectWorld(id)); bump(); }} />
      )}
    </div>
  );
}
