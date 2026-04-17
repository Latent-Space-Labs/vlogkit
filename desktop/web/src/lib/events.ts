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

export type BoardEvent =
  | AnalyzeEvent
  | StoryboardRegenStarted
  | StoryboardRegenToken
  | StoryboardRegenComplete
  | StoryboardRegenFailed;
