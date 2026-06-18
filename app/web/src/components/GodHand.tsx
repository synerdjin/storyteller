import { useState } from "react";
import { api } from "../api";
import type { AgentToken } from "../types";

export function GodHand({ worldId, agents, onDone }: {
  worldId: number; agents: AgentToken[]; onDone: () => void;
}) {
  const [msg, setMsg] = useState("");
  const living = agents.filter((a) => a.living);

  // inject event
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [evAgent, setEvAgent] = useState("");

  // nudge / whisper
  const [target, setTarget] = useState(living[0]?.name || "");
  const [pursue, setPursue] = useState("");
  const [goalTarget, setGoalTarget] = useState("");

  const run = async (payload: Record<string, unknown>, label: string) => {
    try {
      await api.intervene(worldId, payload);
      setMsg(`✓ ${label}`);
      onDone();
    } catch (e) {
      setMsg("✗ " + (e as Error).message);
    }
  };

  return (
    <div className="pane">
      <div className="section-h">Inject an event</div>
      <div className="gh-row"><label>headline</label>
        <input style={{ flex: 1 }} value={headline} onChange={(e) => setHeadline(e.target.value)} /></div>
      <div className="gh-row"><label>detail</label>
        <input style={{ flex: 1 }} value={body} onChange={(e) => setBody(e.target.value)} /></div>
      <div className="gh-row"><label>about</label>
        <select value={evAgent} onChange={(e) => setEvAgent(e.target.value)}>
          <option value="">— no one in particular —</option>
          {living.map((a) => <option key={a.id} value={a.name}>{a.display_name}</option>)}
        </select></div>
      <button className="primary" disabled={!headline}
        onClick={() => run({ action: "inject_event", headline, body, agent: evAgent || null },
          "event injected (ripples next tick)")}>Inject →</button>

      <div className="section-h">Nudge an NPC</div>
      <div className="gh-row"><label>who</label>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          {living.map((a) => <option key={a.id} value={a.name}>{a.display_name}</option>)}
        </select></div>
      <div className="gh-row">
        <button onClick={() => run({ action: "nudge", agent: target, mood_delta: { desperation: 1 } },
          "stoked desperation")}>+ desperation</button>
        <button onClick={() => run({ action: "nudge", agent: target, clock_delta: 1 },
          "advanced clock")}>+ clock</button>
        <button onClick={() => run({ action: "nudge", agent: target, salience: 5 },
          "made loud")}>make loud</button>
        <button onClick={() => run({ action: "nudge", agent: target, kill: true },
          "removed from play")}>✝ kill</button>
      </div>

      <div className="section-h">Whisper a new goal</div>
      <div className="gh-row"><label>who</label>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          {living.map((a) => <option key={a.id} value={a.name}>{a.display_name}</option>)}
        </select></div>
      <div className="gh-row"><label>pursue</label>
        <select value={pursue} onChange={(e) => setPursue(e.target.value)}>
          <option value="">—</option>
          {["control", "protect", "destroy", "seize", "expose", "court", "undermine"].map((p) =>
            <option key={p} value={p}>{p}</option>)}
        </select>
        <label>target</label>
        <select value={goalTarget} onChange={(e) => setGoalTarget(e.target.value)}>
          <option value="">—</option>
          {agents.map((a) => <option key={a.id} value={a.name}>{a.name}</option>)}
        </select>
      </div>
      <button className="primary" disabled={!pursue && !goalTarget}
        onClick={() => run({ action: "whisper_goal", agent: target,
          pursue: pursue || null, target: goalTarget || null }, "goal whispered")}>
        Whisper →</button>

      {msg && <div className="banner" style={{ marginTop: 14 }}>{msg}</div>}
    </div>
  );
}
