import type {
  BackgroundQuestionnaire,
  EUS,
  StudyState,
  TaskView,
  ValidationResult,
} from "./types";

const API_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    throw new Error(
      body?.detail ??
        `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

export function startStudy(
  participantId: string,
): Promise<StudyState> {
  return request("/study/start", {
    method: "POST",
    body: JSON.stringify({
      participant_id: participantId,
    }),
  });
}

export function getStudyState(
  participantId: string,
): Promise<StudyState> {
  return request(`/study/${participantId}`);
}

export function submitBackground(
  participantId: string,
  background: BackgroundQuestionnaire,
): Promise<{ status: string }> {
  return request(
    `/study/${participantId}/background`,
    {
      method: "POST",
      body: JSON.stringify(background),
    },
  );
}

export function openTask(
  participantId: string,
  taskNumber: number,
): Promise<TaskView> {
  return request(
    `/study/${participantId}/tasks/${taskNumber}/open`,
    {
      method: "POST",
    },
  );
}

export function saveEditor(
  participantId: string,
  taskId: string,
  draft: EUS,
  field?: string,
): Promise<{ status: string }> {
  return request(
    `/study/${participantId}/tasks/${taskId}/editor`,
    {
      method: "PUT",
      body: JSON.stringify({
        draft,
        field: field ?? null,
      }),
    },
  );
}

export async function validateEUS(
  participantId: string,
  taskId: string,
): Promise<ValidationResult> {
  const response = await request<{
    validation: ValidationResult;
  }>(
    `/study/${participantId}/tasks/${taskId}/validation`,
    {
      method: "POST",
    },
  );

  return response.validation;
}

export function requestRevision(
  participantId: string,
  taskId: string,
  instruction?: string,
): Promise<{
  interaction_id: string;
  revision: EUS;
}> {
  return request(
    `/study/${participantId}/tasks/${taskId}/revision`,
    {
      method: "POST",
      body: JSON.stringify({
        revision_instruction: instruction || null,
      }),
    },
  );
}

export function acceptRevision(
  participantId: string,
  taskId: string,
  interactionId: string,
): Promise<{
  status: string;
  current_eus: EUS;
}> {
  return request(
    `/study/${participantId}/tasks/${taskId}/revision/${interactionId}/accept`,
    {
      method: "POST",
    },
  );
}

export function rejectRevision(
  participantId: string,
  taskId: string,
  interactionId: string,
): Promise<{ status: string }> {
  return request(
    `/study/${participantId}/tasks/${taskId}/revision/${interactionId}/reject`,
    {
      method: "POST",
    },
  );
}

export function pauseTask(
  participantId: string,
  taskId: string,
): Promise<{ status: string }> {
  return request(
    `/study/${participantId}/tasks/${taskId}/pause`,
    {
      method: "POST",
    },
  );
}

export function resumeTask(
  participantId: string,
  taskId: string,
): Promise<{ status: string }> {
  return request(
    `/study/${participantId}/tasks/${taskId}/resume`,
    {
      method: "POST",
    },
  );
}

export function submitTask(
  participantId: string,
  taskId: string,
  finalEus: EUS,
  inactiveSeconds: number,
): Promise<{
  task: TaskView;
  study_completed: boolean;
}> {
  return request(
    `/study/${participantId}/tasks/${taskId}/submit`,
    {
      method: "POST",
      body: JSON.stringify({
        final_eus: finalEus,
        inactive_seconds: inactiveSeconds,
      }),
    },
  );
}
