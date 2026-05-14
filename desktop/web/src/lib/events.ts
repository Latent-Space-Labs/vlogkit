/**
 * Analyze event types — hand-spelled because WS messages don't appear in
 * the OpenAPI schema. Keep in sync with vlogkit/server/schemas.py.
 */

export type AnalyzeStarted = {
  type: "analyze.started";
  job_id: string;
  clip_count: number;
};
export type AnalyzeProgress = {
  type: "analyze.progress";
  clip_filename: string;
  stage: "metadata" | "transcribe" | "scenes" | "vision" | "audio" | "motion";
  pct: number;
};
export type AnalyzeClipDone = {
  type: "analyze.clip_done";
  clip_filename: string;
  analysis: unknown;
};
export type AnalyzeClipFailed = {
  type: "analyze.clip_failed";
  clip_filename: string;
  error: string;
};
export type AnalyzeComplete = {
  type: "analyze.complete";
  job_id: string;
  duration_s: number;
};

export type AnalyzeEvent =
  | AnalyzeStarted
  | AnalyzeProgress
  | AnalyzeClipDone
  | AnalyzeClipFailed
  | AnalyzeComplete;

export type StoryboardRegenStarted = {
  type: "storyboard.regen_started";
  job_id: string;
};
export type StoryboardRegenToken = {
  type: "storyboard.regen_token";
  token: string;
};
export type StoryboardRegenComplete = {
  type: "storyboard.regen_complete";
  job_id: string;
  storyboard: unknown;
};
export type StoryboardRegenFailed = {
  type: "storyboard.regen_failed";
  job_id: string;
  error: string;
};

// ---- Score events (new) ----

export type ScoreStarted = {
  type: "score.started";
  job_id: string;
  total_scenes: number;
};
export type ScoreProgress = {
  type: "score.progress";
  job_id: string;
  scored: number;
  total_scenes: number;
  current_clip: string;
  current_scene_index: number;
};
export type ScoreClipDone = {
  type: "score.clip_done";
  job_id: string;
  clip_filename: string;
  average_composite: number;
};
export type ScoreComplete = {
  type: "score.complete";
  job_id: string;
  total_scored: number;
};
export type ScoreFailed = {
  type: "score.failed";
  job_id: string;
  error: string;
};

export type ScoreEvent =
  | ScoreStarted
  | ScoreProgress
  | ScoreClipDone
  | ScoreComplete
  | ScoreFailed;

// ---- Storyboard agent stage events (new) ----

export type StoryboardAgentStage = "director" | "editor" | "polisher";

export type StoryboardAgentStarted = {
  type: "storyboard.agent_started";
  job_id: string;
  stage: StoryboardAgentStage;
};
export type StoryboardAgentComplete = {
  type: "storyboard.agent_complete";
  job_id: string;
  stage: StoryboardAgentStage;
  summary: string;
};
export type StoryboardAgentFailed = {
  type: "storyboard.agent_failed";
  job_id: string;
  stage: StoryboardAgentStage;
  reason: string;
};

export type StoryboardAgentEvent =
  | StoryboardAgentStarted
  | StoryboardAgentComplete
  | StoryboardAgentFailed;

export type BoardEvent =
  | AnalyzeEvent
  | ScoreEvent
  | StoryboardRegenStarted
  | StoryboardRegenToken
  | StoryboardRegenComplete
  | StoryboardRegenFailed
  | StoryboardAgentEvent;
