import { useEffect, useState } from "react";
import { api } from "../api";
import type { AgentDetail } from "../types";

export function Inspector({
  worldId, agentId, curtain, directorsAvailable, onChanged,
}: {
  worldId: number;
  agentId: number;
  curtain: boolean;
  directorsAvailable: boolean;
  onChanged: () => void;
}) {
  const [a, setA] = useState<AgentDetail | null>(null);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [says, setSays] = useState("");
  const [line, setLine] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setA(null);
    api.agent(agentId, curtain).then(setA);
  }, [agentId, curtain]);

  if (!a) return <div className="pane faint">loading…</div>;

  const relClass = (w: number) => (w < 0 ? "rel-rival" : w > 0 ? "rel-ally" : "");

  const speak = async () => {
    setBusy(true);
    setLine("");
    try {
      const r = await api.voice(worldId, a.name, "", says);
      setLine(r.line);
    } catch (e) {
      setLine("(" + (e as Error).message + ")");
    }
    setBusy(false);
  };

  return (
    <div className="pane">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{a.display_name}</h3>
        <span className="faint">{a.living ? a.state : "✝ gone"}</span>
      </div>
      <div className="muted" style={{ fontSize: 12 }}>
        {a.kind} · salience {a.salience}
      </div>

      <div className="section-h">Profile (openly known)</div>
      <pre className="prose">{a.profile_md || "(a sketch)"}</pre>

      {a.observations.length > 0 && (
        <>
          <div className="section-h">What they've heard</div>
          {a.observations.map((o, i) => <div key={i} className="muted" style={{ fontSize: 12 }}>• {o}</div>)}
        </>
      )}

      {directorsAvailable && a.living && (
        <>
          <div className="section-h">Possess / voice</div>
          {!voiceOpen ? (
            <button onClick={() => setVoiceOpen(true)}>Speak to them →</button>
          ) : (
            <>
              <input style={{ width: "100%" }} placeholder="say something to them…"
                value={says} onChange={(e) => setSays(e.target.value)} />
              <button className="primary" disabled={busy} style={{ marginTop: 6 }} onClick={speak}>
                {busy ? "…" : "Voice them"}
              </button>
              {line && <pre className="prose" style={{ marginTop: 8 }}>{line}</pre>}
            </>
          )}
        </>
      )}

      {/* ── behind the curtain ── */}
      {a.curtained ? (
        <div className="banner" style={{ margin: "16px 0 0" }}>
          🔴 There is more behind the curtain — flip it on to read their mind.
        </div>
      ) : (
        <div className="secret">
          <div className="section-h">🔴 Drive (hidden)</div>
          <div className="kv">
            <span className="k">goal</span>
            <span>{a.goal?.pursue} → <b>{a.goal?.target}</b></span>
            <span className="k">success</span><span>{a.goal?.success || "—"}</span>
            <span className="k">clock</span><span>{a.clock?.filled}/{a.clock?.total} ({a.advances_when})</span>
            {a.group && <><span className="k">group</span><span>{a.group}</span></>}
          </div>
          {a.resources && Object.keys(a.resources).length > 0 && (
            <div>{Object.entries(a.resources).map(([k, v]) => (
              <span className="pill" key={k}>{k} {v}</span>))}</div>
          )}
          {a.mood && Object.keys(a.mood).length > 0 && (
            <div>{Object.entries(a.mood).map(([k, v]) => (
              <span className="pill" key={k}>{k} {v}</span>))}</div>
          )}

          {a.relationships && a.relationships.length > 0 && (
            <>
              <div className="section-h">🔴 Relationships</div>
              {a.relationships.map((r, i) => (
                <div key={i} style={{ marginBottom: 4 }}>
                  <span className={`pill ${relClass(r.weight)}`}>{r.tie} {r.weight}</span>
                  <b>{r.target_ref}</b>
                  {r.note && <div className="faint" style={{ fontSize: 11 }}>{r.note}</div>}
                </div>
              ))}
            </>
          )}

          {a.secrets_md && (<><div className="section-h">🔴 Secrets</div>
            <pre className="prose">{a.secrets_md}</pre></>)}
          {a.drives_prose_md && (<><div className="section-h">🔴 Agenda / beliefs</div>
            <pre className="prose">{a.drives_prose_md}</pre></>)}
          {a.sheet_md && (<><div className="section-h">🔴 Sheet</div>
            <pre className="prose">{a.sheet_md}</pre></>)}
        </div>
      )}
    </div>
  );
}
