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
  strategy?: string;  // "retry" | "recovery"
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
  taskStreamingText: Record<string, string>;
  taskTimedOut: Record<string, boolean>;
  failureReason: string | null;
  sseConnected: boolean;
  actionCost: number;  // total_cost_usd accumulated via SSE
  costByTask: Record<string, number>;  // task_id -> cost_usd
  costByModel: Record<string, { cost_usd: number; calls: number }>;

  setTaskOverride: (taskId: string, override: Partial<Task>) => void;
  setActionStatus: (status: string) => void;
  setRecoveryAttempt: (attempt: number | null) => void;
  setReplanning: (v: boolean) => void;
  setFailureReason: (reason: string | null) => void;
  setSSEConnected: (connected: boolean) => void;
  clearTaskState: () => void;
  appendTaskLog: (taskId: string, log: { level: string; message: string }) => void;
  resetForAction: (actionId: string) => void;
  resetLogs: (taskId: string) => void;
  setCodeExecution: (taskId: string, data: Partial<CodeExecutionState>) => void;
  addIteration: (taskId: string, iteration: AgentIteration) => void;
  updateCurrentIteration: (taskId: string, info: Partial<CurrentIterationInfo>) => void;
  setRetryStatus: (taskId: string, status: RetryStatus | null) => void;
  appendTaskStreamingText: (taskId: string, chunk: string) => void;
  setTaskTimedOut: (taskId: string, timedOut: boolean) => void;
  updateCost: (totalCost: number, taskId: string | null, model: string | null, costUsd: number) => void;
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
  taskStreamingText: {},
  taskTimedOut: {},
  failureReason: null,
  sseConnected: true,
  actionCost: 0,
  costByTask: {},
  costByModel: {},

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

  setFailureReason: (reason) =>
    set({ failureReason: reason }),

  setSSEConnected: (connected) =>
    set({ sseConnected: connected }),

  clearTaskState: () =>
    set({ taskOverrides: {}, taskLogs: {}, codeExecutions: {}, taskIterations: {}, currentIteration: {}, retryStatus: {}, taskStreamingText: {}, taskTimedOut: {}, failureReason: null, actionCost: 0, costByTask: {}, costByModel: {} }),

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
      taskStreamingText: {},
      taskTimedOut: {},
      failureReason: null,
      sseConnected: true,
      actionCost: 0,
      costByTask: {},
      costByModel: {},
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

  appendTaskStreamingText: (taskId, chunk) =>
    set((state) => ({
      taskStreamingText: {
        ...state.taskStreamingText,
        [taskId]: (state.taskStreamingText[taskId] || "") + chunk,
      },
    })),

  setTaskTimedOut: (taskId, timedOut) =>
    set((state) => ({
      taskTimedOut: {
        ...state.taskTimedOut,
        [taskId]: timedOut,
      },
    })),

  updateCost: (totalCost, taskId, model, costUsd) =>
    set((state) => {
      const costByTask = taskId
        ? { ...state.costByTask, [taskId]: (state.costByTask[taskId] || 0) + costUsd }
        : state.costByTask;
      const costByModel = model
        ? {
            ...state.costByModel,
            [model]: {
              cost_usd: (state.costByModel[model]?.cost_usd || 0) + costUsd,
              calls: (state.costByModel[model]?.calls || 0) + 1,
            },
          }
        : state.costByModel;
      return { actionCost: totalCost, costByTask, costByModel };
    }),
}));
