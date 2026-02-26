import { create } from "zustand";
import type { AgentIteration, CodeExecutionState, Task } from "@/types";

export interface CurrentIterationInfo {
  iteration_number: number;
  reasoning: string | null;
  tool: string | null;
  status: "running" | "tool_calling" | "completed" | "failed";
}

export interface RetryStatus {
  attempt: number;
  max_attempts: number;
}

interface ActionStore {
  // Scoped to the currently viewed action
  currentActionId: string;
  taskOverrides: Record<string, Partial<Task>>;
  actionStatus: string | null;
  recoveryAttempt: number | null;  // set when action.retrying fires
  isReplanning: boolean;           // set when action.replanning fires
  taskLogs: Record<string, { level: string; message: string; timestamp: string }[]>;
  codeExecutions: Record<string, CodeExecutionState>;
  taskIterations: Record<string, AgentIteration[]>;
  currentIteration: Record<string, CurrentIterationInfo>;
  retryStatus: Record<string, RetryStatus>;

  setTaskOverride: (taskId: string, override: Partial<Task>) => void;
  setActionStatus: (status: string) => void;
  setRecoveryAttempt: (attempt: number | null) => void;
  setReplanning: (v: boolean) => void;
  clearTaskState: () => void;
  appendTaskLog: (taskId: string, log: { level: string; message: string }) => void;
  resetForAction: (actionId: string) => void;
  resetLogs: (taskId: string) => void;
  setCodeExecution: (taskId: string, data: Partial<CodeExecutionState>) => void;
  addIteration: (taskId: string, iteration: AgentIteration) => void;
  updateCurrentIteration: (taskId: string, info: Partial<CurrentIterationInfo>) => void;
  setRetryStatus: (taskId: string, status: RetryStatus | null) => void;
}

const defaultCodeState: CodeExecutionState = {
  status: "idle",
  stdout: "",
  stderr: "",
  artifactIds: [],
};

export const useActionStore = create<ActionStore>((set, get) => ({
  currentActionId: "",
  taskOverrides: {},
  actionStatus: null,
  recoveryAttempt: null,
  isReplanning: false,
  taskLogs: {},
  codeExecutions: {},
  taskIterations: {},
  currentIteration: {},
  retryStatus: {},

  setTaskOverride: (taskId, override) =>
    set((state) => ({
      taskOverrides: {
        ...state.taskOverrides,
        [taskId]: { ...state.taskOverrides[taskId], ...override },
      },
    })),

  setActionStatus: (status) =>
    set({ actionStatus: status }),

  setRecoveryAttempt: (attempt) =>
    set({ recoveryAttempt: attempt }),

  setReplanning: (v) =>
    set({ isReplanning: v }),

  clearTaskState: () =>
    set({ taskOverrides: {}, taskLogs: {}, codeExecutions: {}, taskIterations: {}, currentIteration: {}, retryStatus: {} }),

  appendTaskLog: (taskId, log) =>
    set((state) => ({
      taskLogs: {
        ...state.taskLogs,
        [taskId]: [
          ...(state.taskLogs[taskId] || []),
          { ...log, timestamp: new Date().toISOString() },
        ],
      },
    })),

  resetForAction: (actionId) =>
    set({
      currentActionId: actionId,
      taskOverrides: {},
      actionStatus: null,
      recoveryAttempt: null,
      isReplanning: false,
      taskLogs: {},
      codeExecutions: {},
      taskIterations: {},
      currentIteration: {},
      retryStatus: {},
    }),

  resetLogs: (taskId) =>
    set((state) => {
      const newLogs = { ...state.taskLogs };
      delete newLogs[taskId];
      return { taskLogs: newLogs };
    }),

  setCodeExecution: (taskId, data) =>
    set((state) => ({
      codeExecutions: {
        ...state.codeExecutions,
        [taskId]: {
          ...(state.codeExecutions[taskId] || defaultCodeState),
          ...data,
        },
      },
    })),

  addIteration: (taskId, iteration) =>
    set((state) => ({
      taskIterations: {
        ...state.taskIterations,
        [taskId]: [...(state.taskIterations[taskId] || []), iteration],
      },
    })),

  updateCurrentIteration: (taskId, info) =>
    set((state) => ({
      currentIteration: {
        ...state.currentIteration,
        [taskId]: {
          ...(state.currentIteration[taskId] || { iteration_number: 0, reasoning: null, tool: null, status: "running" as const }),
          ...info,
        },
      },
    })),

  setRetryStatus: (taskId, status) =>
    set((state) => {
      if (status === null) {
        const next = { ...state.retryStatus };
        delete next[taskId];
        return { retryStatus: next };
      }
      return {
        retryStatus: { ...state.retryStatus, [taskId]: status },
      };
    }),
}));
