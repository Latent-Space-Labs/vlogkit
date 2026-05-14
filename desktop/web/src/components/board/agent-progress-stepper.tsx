"use client";

import { useEffect } from "react";
import type { StoryboardAgentStage } from "@/lib/events";

export type StepStatus = "pending" | "active" | "done" | "failed";

export interface StepState {
  status: StepStatus;
  summary: string;
}

export type AgentSteps = Record<StoryboardAgentStage, StepState>;

export const INITIAL_AGENT_STEPS: AgentSteps = {
  director: { status: "pending", summary: "" },
  editor: { status: "pending", summary: "" },
  polisher: { status: "pending", summary: "" },
};

const STAGES: StoryboardAgentStage[] = ["director", "editor", "polisher"];
const STAGE_TITLES: Record<StoryboardAgentStage, string> = {
  director: "Director",
  editor: "Editor",
  polisher: "Polisher",
};

export function AgentProgressStepper({
  steps,
  onComplete,
}: {
  steps: AgentSteps;
  onComplete?: () => void;
}) {
  // Fire onComplete shortly after polisher reaches done
  useEffect(() => {
    if (steps.polisher.status === "done") {
      const t = setTimeout(() => onComplete?.(), 800);
      return () => clearTimeout(t);
    }
  }, [steps.polisher.status, onComplete]);

  const anyFailed = STAGES.some((s) => steps[s].status === "failed");

  return (
    <div className="bg-white border border-[var(--color-border-whisper)] rounded-lg p-4 flex items-center gap-0">
      {STAGES.map((stage, i) => (
        <span key={stage} className="flex items-center flex-1">
          <Step number={i + 1} title={STAGE_TITLES[stage]} state={steps[stage]} />
          {i < STAGES.length - 1 && (
            <span
              className={`flex-shrink-0 mx-2 h-0.5 w-8 ${
                steps[stage].status === "done" ? "bg-emerald-500" : "bg-gray-200"
              }`}
            />
          )}
        </span>
      ))}
      {anyFailed && (
        <p className="text-xs text-red-700 mt-2 ml-2 flex-1">
          Falling back to chronological order.
        </p>
      )}
    </div>
  );
}

function Step({
  number,
  title,
  state,
}: {
  number: number;
  title: string;
  state: StepState;
}) {
  const circleClass =
    state.status === "done"
      ? "bg-emerald-500 text-white"
      : state.status === "active"
      ? "bg-blue-500 text-white"
      : state.status === "failed"
      ? "bg-red-500 text-white"
      : "bg-gray-200 text-[var(--color-muted)]";

  const subtitle =
    state.status === "active"
      ? "running…"
      : state.status === "done"
      ? state.summary || "done"
      : state.status === "failed"
      ? state.summary
      : "pending";

  const subtitleClass =
    state.status === "active"
      ? "text-blue-700"
      : state.status === "failed"
      ? "text-red-700"
      : "text-[var(--color-muted)]";

  return (
    <span className="flex items-center gap-2">
      <span
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${circleClass}`}
      >
        {state.status === "done" ? "✓" : state.status === "failed" ? "✕" : number}
      </span>
      <span>
        <span className="block text-xs font-semibold">{title}</span>
        <span className={`block text-[10px] ${subtitleClass}`}>{subtitle}</span>
      </span>
    </span>
  );
}
