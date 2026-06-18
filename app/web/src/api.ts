import type {
  AgentDetail, Development, LedgerView, MapData, Plot, WorldSnapshot, WorldSummary,
} from "./types";

const J = async (r: Response) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

const cq = (curtain: boolean) => (curtain ? "?curtain=true" : "");

export const api = {
  status: (): Promise<{ ok: boolean; directors_available: boolean }> =>
    fetch("/api/status").then(J),

  listWorlds: (): Promise<WorldSummary[]> => fetch("/api/worlds").then(J),

  createDemo: (): Promise<{ world_id: number }> =>
    fetch("/api/worlds/demo", { method: "POST" }).then(J),

  createWorld: (params: Record<string, unknown>): Promise<{ world_id: number; summary?: string }> =>
    fetch("/api/worlds", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(params),
    }).then(J),

  world: (id: number, curtain: boolean): Promise<WorldSnapshot> =>
    fetch(`/api/worlds/${id}${cq(curtain)}`).then(J),

  map: (id: number): Promise<MapData> => fetch(`/api/worlds/${id}/map`).then(J),

  agent: (id: number, curtain: boolean): Promise<AgentDetail> =>
    fetch(`/api/agents/${id}${cq(curtain)}`).then(J),

  developments: (id: number, curtain: boolean): Promise<Development[]> =>
    fetch(`/api/worlds/${id}/developments${cq(curtain)}`).then(J),

  ledgers: (id: number, curtain: boolean): Promise<{ curtained: boolean; ledgers: LedgerView[] }> =>
    fetch(`/api/worlds/${id}/ledgers${cq(curtain)}`).then(J),

  plots: (id: number, curtain: boolean): Promise<Plot[]> =>
    fetch(`/api/worlds/${id}/plots${cq(curtain)}`).then(J),

  intervene: (id: number, body: Record<string, unknown>): Promise<unknown> =>
    fetch(`/api/worlds/${id}/intervene`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(J),

  voice: (id: number, name: string, scene: string, says: string): Promise<{ line: string }> =>
    fetch(`/api/worlds/${id}/agents/${name}/voice`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scene, says }),
    }).then(J),
};

// SSE-ish reader for the tick endpoint (POST + streamed body, parsed as SSE).
export async function tickStream(
  worldId: number,
  params: Record<string, unknown>,
  onEvent: (event: string, data: any) => void,
): Promise<void> {
  const resp = await fetch(`/api/worlds/${worldId}/tick`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!resp.body) throw new Error("no stream");
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const blocks = buf.split("\n\n");
    buf = blocks.pop() || "";
    for (const block of blocks) {
      let ev = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) {
        try { onEvent(ev, JSON.parse(data)); } catch { /* ignore */ }
      }
    }
  }
}
