import { useState } from "react";
import { api } from "../api";

const GAMES = [
  { id: "v20", label: "Vampire (V20) — personal horror" },
  { id: "m20", label: "Mage (M20) — ascension horror" },
  { id: "w20", label: "Werewolf (W20) — primal horror" },
];

export function Wizard({ directorsAvailable, onCreated, onClose }: {
  directorsAvailable: boolean;
  onCreated: (worldId: number) => void;
  onClose: () => void;
}) {
  const [game, setGame] = useState("v20");
  const [tone, setTone] = useState("noir, slow-burn dread");
  const [premise, setPremise] = useState("");
  const [lethality, setLethality] = useState("medium");
  const [playMode, setPlayMode] = useState("dramatist");
  const [npc, setNpc] = useState(6);
  const [collisions, setCollisions] = useState(3);
  const [locations, setLocations] = useState(5);
  const [factions, setFactions] = useState(2);
  const [loud, setLoud] = useState(2);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const create = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.createWorld({
        game, tone, premise, lethality, play_mode: playMode,
        npc_count: npc, collision_count: collisions, location_count: locations,
        faction_count: factions, loud_count: loud,
      });
      onCreated(r.world_id);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  const demo = async () => {
    setBusy(true);
    const r = await api.createDemo();
    onCreated(r.world_id);
  };

  const Range = ({ label, val, set, min, max }: {
    label: string; val: number; set: (n: number) => void; min: number; max: number;
  }) => (
    <div className="field">
      <label>{label}: <span className="range-val">{val}</span></label>
      <input type="range" min={min} max={max} value={val}
        onChange={(e) => set(+e.target.value)} />
    </div>
  );

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>New world</h2>
        {!directorsAvailable && (
          <div className="banner">
            No <code>ANTHROPIC_API_KEY</code> set — the architect can't generate a world.
            You can still load the <b>deterministic demo world</b> below.
          </div>
        )}

        <div className="field">
          <label>Game</label>
          <select value={game} onChange={(e) => setGame(e.target.value)}>
            {GAMES.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
          </select>
        </div>
        <div className="field"><label>Tone</label>
          <input value={tone} onChange={(e) => setTone(e.target.value)} /></div>
        <div className="field"><label>Premise (optional — the architect fills gaps)</label>
          <textarea rows={2} value={premise} onChange={(e) => setPremise(e.target.value)} /></div>
        <div style={{ display: "flex", gap: 10 }}>
          <div className="field" style={{ flex: 1 }}><label>Lethality</label>
            <select value={lethality} onChange={(e) => setLethality(e.target.value)}>
              {["low", "medium", "high"].map((l) => <option key={l}>{l}</option>)}
            </select></div>
          <div className="field" style={{ flex: 1 }}><label>Play mode</label>
            <select value={playMode} onChange={(e) => setPlayMode(e.target.value)}>
              {["dramatist", "simulationist", "evaluationist"].map((m) => <option key={m}>{m}</option>)}
            </select></div>
        </div>

        <div className="section-h">World size</div>
        <Range label="NPCs" val={npc} set={setNpc} min={3} max={20} />
        <Range label="Latent collisions to seed" val={collisions} set={setCollisions} min={1} max={8} />
        <Range label="Locations" val={locations} set={setLocations} min={2} max={10} />
        <Range label="Factions" val={factions} set={setFactions} min={0} max={5} />
        <Range label="NPCs that start loud" val={loud} set={setLoud} min={0} max={npc} />

        {err && <div className="banner">✗ {err}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="primary" disabled={busy || !directorsAvailable} onClick={create}>
            {busy ? "Seeding the world…" : "Generate world →"}
          </button>
          <button disabled={busy} onClick={demo}>Load demo world</button>
          <div className="grow" style={{ flex: 1 }} />
          <button disabled={busy} onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
