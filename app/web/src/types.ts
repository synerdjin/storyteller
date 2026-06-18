export interface WorldSummary {
  id: number;
  name: string;
  game: string;
  current_day: number;
  agents: number;
}

export interface WorldSnapshot {
  id: number;
  name: string;
  game: string;
  edition: string;
  play_mode: string;
  tone: string;
  premise: string;
  lethality: string;
  current_day: number;
  agent_count: number;
  gm_secrets_md?: string;
}

export interface AgentToken {
  id: number;
  name: string;
  display_name: string;
  living: boolean;
  salience: number;
  location_id: number | null;
  kind: string;
}

export interface MapLocation {
  id: number;
  name: string;
  description: string;
  x: number;
  y: number;
}

export interface MapData {
  locations: MapLocation[];
  agents: AgentToken[];
}

export interface Relationship {
  target_ref: string;
  tie: string;
  weight: number;
  note?: string;
}

export interface AgentDetail {
  id: number;
  name: string;
  display_name: string;
  kind: string;
  living: boolean;
  state: string;
  salience: number;
  location_id: number | null;
  profile_md: string;
  observations: string[];
  memory: string[];
  curtained: boolean;
  // behind the curtain:
  goal?: { pursue: string; target: string; success: string };
  clock?: { filled: number; total: number };
  advances_when?: string;
  group?: string;
  resources?: Record<string, number>;
  mood?: Record<string, number>;
  relationships?: Relationship[];
  states?: { from_state: string; to_state: string; guard: string }[];
  secrets_md?: string;
  sheet_md?: string;
  drives_prose_md?: string;
}

export interface Development {
  id: number;
  day: number;
  agent: string | null;
  headline: string;
  body: string;
  surface: string;
  tier: "public" | "emerging" | "hidden";
  escalate: boolean;
  drained: boolean;
  source: string;
  arc: string | null;
}

export interface LedgerView {
  entity: string;
  total: number;
  holder: string | null;
  phase: string;
  standing: string;
  control: Record<string, number>;
  history: string[];
}

export interface Plot {
  id: number;
  plot_key: string;
  title: string;
  participants: string;
  stakes: string;
  state: string;
  surface: string;
  arc: string | null;
  body_md: string;
}
