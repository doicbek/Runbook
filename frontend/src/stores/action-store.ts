import { create } from "zustand";
import type { CodeExecutionState, Task } from "@/types";

interface ActionStore {
  // Scoped to the currently viewed action
  currentActionId: string;
  taskOverrides: Record<string, Partial<Task>>;
  actionStatus: string | null;
  recoveryAttempt: number | null;  // set when action.retrying fires
  taskLogs: Record<string, { level: string; message: string; timestamp: string }[]>;
  codeExecutions: Record<string, CodeExecutionState>;

  setTaskOverride: (taskId: string, override: Partial<Task>) => void;
  setActionStatus: (status: string) => void;
  setRecoveryAttempt: (attempt: number | null) => void;
  appendTaskLog: (taskId: string, log: { level: string; message: string }) => void;
  resetForAction: (actionId: string) => void;
  resetLogs: (taskId: string) => void;
  setCodeExecution: (taskId: string, data: Partial<CodeExecutionState>) => void;
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
  taskLogs: {},
  codeExecutions: {},

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
      taskLogs: {},
      codeExecutions: {},
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
}));
