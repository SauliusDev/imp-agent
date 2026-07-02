export type CurrentStep = {
  story_id: string;
  step: string;
  attempt: number;
  max_attempts: number;
  step_chain: string;
  start_time?: number;
  elapsed_s: number;
  log_path: string;
  tmux_session: string | null;
};

export type UsageState = {
  five_hour_pct: number | null;
  seven_day_pct: number | null;
  sonnet_pct: number | null;
  extra_pct?: number | null;
  extra_spent_eur?: string | null;
  extra_account_cap_eur?: string | null;
  decision?: string;
  five_hour_resets_at?: number | null;
  seven_day_resets_at?: number | null;
  updated_at: number | null;
};

export type RoadmapRow = [type: string, id: string, status: string, detail: string, blocked_reason: string | null];

export type ImpState = {
  epic_id: string;
  provider: string;
  app_phase: string;
  halted: boolean;
  halt_reason: string | null;
  should_exit: boolean;
  exit_code: number;
  usage: UsageState;
  current: CurrentStep | null;
  pending_stories: string[];
  roadmap_rows: RoadmapRow[];
  output_lines: string[];
};

export type ControlAction = "run" | "pause" | "resume" | "quit" | "reload-config";
