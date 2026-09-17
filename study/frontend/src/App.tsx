import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  acceptRevision,
  openTask,
  pauseTask,
  rejectRevision,
  requestRevision,
  resumeTask,
  saveEditor,
  startStudy,
  submitTask,
  validateEUS,
} from "./api";

import type {
  EUS,
  TaskView,
  ValidationResult,
} from "./types";

import "./styles.css";

const EMPTY_EUS: EUS = {
  title: "",
  description: "",
  work_items: [""],
};

function App() {
  const [participantId, setParticipantId] = useState(
    localStorage.getItem("participant_id") ?? "",
  );

  const [started, setStarted] = useState(false);
  const [task, setTask] = useState<TaskView | null>(null);
  const [draft, setDraft] = useState<EUS>(EMPTY_EUS);

  const [validation, setValidation] =
    useState<ValidationResult | null>(null);

  const [revision, setRevision] = useState<{
    interactionId: string;
    eus: EUS;
  } | null>(null);

  const [revisionInstruction, setRevisionInstruction] =
    useState("");

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);

  const inactiveStartedAt = useRef<number | null>(null);
  const inactiveSeconds = useRef(0);
  const saveTimer = useRef<number | null>(null);

  async function handleStart() {
    const normalized = participantId.trim().toUpperCase();

    if (!normalized) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const state = await startStudy(normalized);

      localStorage.setItem(
        "participant_id",
        normalized,
      );

      setParticipantId(normalized);
      setStarted(true);

      if (state.next_task_number === null) {
        setComplete(true);
        return;
      }

      const nextTask = await openTask(
        normalized,
        state.next_task_number,
      );

      loadTask(nextTask);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not start the study.",
      );
    } finally {
      setLoading(false);
    }
  }

  function loadTask(nextTask: TaskView) {
    setTask(nextTask);

    setDraft(
      nextTask.current_eus ?? EMPTY_EUS,
    );

    setValidation(nextTask.validation);
    setRevision(null);
    setRevisionInstruction("");

    inactiveSeconds.current = 0;
    inactiveStartedAt.current = null;
  }

  function updateDraft(
    nextDraft: EUS,
    field: string,
  ) {
    setDraft(nextDraft);

    if (!task) {
      return;
    }

    if (saveTimer.current !== null) {
      window.clearTimeout(saveTimer.current);
    }

    saveTimer.current = window.setTimeout(
      async () => {
        try {
          setSaving(true);

          await saveEditor(
            participantId,
            task.task_id,
            nextDraft,
            field,
          );
        } catch (err) {
          console.error(err);
        } finally {
          setSaving(false);
        }
      },
      700,
    );
  }

  function updateWorkItem(
    index: number,
    value: string,
  ) {
    const workItems = [...draft.work_items];
    workItems[index] = value;

    updateDraft(
      {
        ...draft,
        work_items: workItems,
      },
      "work_items",
    );
  }

  function addWorkItem() {
    updateDraft(
      {
        ...draft,
        work_items: [...draft.work_items, ""],
      },
      "work_items",
    );
  }

  function removeWorkItem(index: number) {
    if (draft.work_items.length === 1) {
      return;
    }

    updateDraft(
      {
        ...draft,
        work_items: draft.work_items.filter(
          (_, itemIndex) => itemIndex !== index,
        ),
      },
      "work_items",
    );
  }

  async function handleValidation() {
    if (!task) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await saveEditor(
        participantId,
        task.task_id,
        draft,
      );

      const result = await validateEUS(
        participantId,
        task.task_id,
      );

      setValidation(result);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Validation failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRevision() {
    if (!task) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await saveEditor(
        participantId,
        task.task_id,
        draft,
      );

      const result = await requestRevision(
        participantId,
        task.task_id,
        revisionInstruction,
      );

      setRevision({
        interactionId: result.interaction_id,
        eus: result.revision,
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Revision failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleAcceptRevision() {
    if (!task || !revision) {
      return;
    }

    setLoading(true);

    try {
      const result = await acceptRevision(
        participantId,
        task.task_id,
        revision.interactionId,
      );

      setDraft(result.current_eus);
      setRevision(null);
      setValidation(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not accept revision.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRejectRevision() {
    if (!task || !revision) {
      return;
    }

    setLoading(true);

    try {
      await rejectRevision(
        participantId,
        task.task_id,
        revision.interactionId,
      );

      setRevision(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not reject revision.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (!task) {
      return;
    }

    const cleaned: EUS = {
      title: draft.title.trim(),
      description: draft.description.trim(),
      work_items: draft.work_items
        .map((item) => item.trim())
        .filter(Boolean),
    };

    if (
      !cleaned.title ||
      !cleaned.description ||
      cleaned.work_items.length === 0
    ) {
      setError(
        "Complete the title, description, and at least one work item before submitting.",
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await submitTask(
        participantId,
        task.task_id,
        cleaned,
        inactiveSeconds.current,
      );

      if (result.study_completed) {
        setTask(null);
        setComplete(true);
        return;
      }

      const nextTaskNumber =
        task.task_number + 1;

      const nextTask = await openTask(
        participantId,
        nextTaskNumber,
      );

      loadTask(nextTask);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not submit task.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!task) {
      return;
    }

    async function handleVisibilityChange() {
      if (document.hidden) {
        inactiveStartedAt.current = Date.now();

        try {
          await pauseTask(
            participantId,
            task.task_id,
          );
        } catch {
          return;
        }
      } else if (inactiveStartedAt.current !== null) {
        inactiveSeconds.current +=
          (Date.now() -
            inactiveStartedAt.current) /
          1000;

        inactiveStartedAt.current = null;

        try {
          await resumeTask(
            participantId,
            task.task_id,
          );
        } catch {
          return;
        }
      }
    }

    document.addEventListener(
      "visibilitychange",
      handleVisibilityChange,
    );

    return () => {
      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
    };
  }, [participantId, task]);

  if (!started) {
    return (
      <main className="start-page">
        <div className="start-card">
          <h1>EAI-USG Study</h1>

          <p>
            Enter the participant ID provided by
            the researcher to begin or continue
            the study.
          </p>

          <input
            value={participantId}
            onChange={(event) =>
              setParticipantId(
                event.target.value,
              )
            }
            placeholder="Participant ID"
          />

          <button
            onClick={handleStart}
            disabled={loading}
          >
            {loading
              ? "Loading..."
              : "Begin study"}
          </button>

          {error && (
            <p className="error">{error}</p>
          )}
        </div>
      </main>
    );
  }

  if (complete) {
    return (
      <main className="start-page">
        <div className="start-card">
          <h1>Study completed</h1>

          <p>
            Thank you for participating. Your
            responses have been recorded.
          </p>
        </div>
      </main>
    );
  }

  if (!task) {
    return null;
  }

  const assisted =
    task.condition === "eai_usg";

  return (
    <main className="study-page">
      <header className="study-header">
        <div>
          <strong>
            Task {task.task_number} of 6
          </strong>

          <span>{task.principle}</span>
        </div>

        <div className="condition">
          {assisted
            ? "EAI-USG-assisted"
            : "Structured manual authoring"}
        </div>
      </header>

      <section className="requirement-card">
        <h2>Ethical requirement</h2>
        <p>{task.requirement.text}</p>
      </section>

      <div className="workspace">
        <section className="editor">
          <div className="section-heading">
            <h2>Ethical User Story</h2>
            <span>
              {saving ? "Saving..." : "Saved"}
            </span>
          </div>

          <label>
            Title
            <input
              value={draft.title}
              onChange={(event) =>
                updateDraft(
                  {
                    ...draft,
                    title: event.target.value,
                  },
                  "title",
                )
              }
            />
          </label>

          <label>
            Description
            <textarea
              value={draft.description}
              rows={4}
              onChange={(event) =>
                updateDraft(
                  {
                    ...draft,
                    description:
                      event.target.value,
                  },
                  "description",
                )
              }
            />
          </label>

          <div className="work-items">
            <div className="section-heading">
              <label>Work items</label>

              <button
                className="secondary small"
                onClick={addWorkItem}
              >
                Add item
              </button>
            </div>

            {draft.work_items.map(
              (item, index) => (
                <div
                  className="work-item"
                  key={index}
                >
                  <span>{index + 1}.</span>

                  <textarea
                    value={item}
                    rows={2}
                    onChange={(event) =>
                      updateWorkItem(
                        index,
                        event.target.value,
                      )
                    }
                  />

                  <button
                    className="remove"
                    onClick={() =>
                      removeWorkItem(index)
                    }
                    disabled={
                      draft.work_items.length ===
                      1
                    }
                  >
                    ×
                  </button>
                </div>
              ),
            )}
          </div>
        </section>

        {assisted && (
          <aside className="ai-panel">
            <h2>EAI-USG support</h2>

            {task.initial_traceability && (
              <details>
                <summary>
                  Initial traceability
                </summary>

                <h3>Source obligations</h3>

                {task.initial_traceability.analysis.obligations.map(
                  (obligation) => (
                    <div
                      className="obligation"
                      key={obligation.id}
                    >
                      <strong>
                        {obligation.id}
                      </strong>
                      <p>{obligation.text}</p>
                    </div>
                  ),
                )}

                <h3>Description</h3>

                <p>
                  {task.initial_traceability.traceability.description_obligation_ids.join(
                    ", ",
                  ) || "No obligation links"}
                </p>

                <h3>Work items</h3>

                {task.initial_traceability.traceability.work_items.map(
                  (trace) => (
                    <div
                      className="trace"
                      key={trace.work_item_index}
                    >
                      <strong>
                        Item{" "}
                        {trace.work_item_index +
                          1}
                        :{" "}
                        {trace.obligation_ids.join(
                          ", ",
                        ) ||
                          "No obligation links"}
                      </strong>

                      <p>
                        {trace.explanation}
                      </p>
                    </div>
                  ),
                )}
              </details>
            )}

            <div className="ai-action">
              <h3>Validation</h3>

              <button
                onClick={handleValidation}
                disabled={
                  loading ||
                  task.validation_used
                }
              >
                {task.validation_used
                  ? "Validation used"
                  : "Validate current EUS"}
              </button>
            </div>

            {validation && (
              <div className="validation">
                <h3>Validation results</h3>

                <div className="scores">
                  <span>
                    Clarity{" "}
                    {validation.clarity}/5
                  </span>
                  <span>
                    Completeness{" "}
                    {
                      validation.completeness
                    }
                    /5
                  </span>
                  <span>
                    Actionability{" "}
                    {
                      validation.actionability
                    }
                    /5
                  </span>
                  <span>
                    Testability{" "}
                    {
                      validation.testability
                    }
                    /5
                  </span>
                  <span>
                    Faithfulness{" "}
                    {
                      validation.faithfulness
                    }
                    /5
                  </span>
                </div>

                {validation.issues.length >
                0 ? (
                  validation.issues.map(
                    (issue, index) => (
                      <div
                        className="issue"
                        key={index}
                      >
                        <strong>
                          {issue.dimension} —{" "}
                          {issue.severity}
                        </strong>

                        <p>{issue.problem}</p>

                        <small>
                          Revision objective:{" "}
                          {
                            issue.recommended_change
                          }
                        </small>
                      </div>
                    ),
                  )
                ) : (
                  <p>
                    No substantive issues
                    identified.
                  </p>
                )}
              </div>
            )}

            <div className="ai-action">
              <h3>AI revision</h3>

              <textarea
                placeholder="Optional revision instruction"
                value={revisionInstruction}
                onChange={(event) =>
                  setRevisionInstruction(
                    event.target.value,
                  )
                }
                disabled={
                  !validation ||
                  task.revision_used
                }
              />

              <button
                onClick={handleRevision}
                disabled={
                  loading ||
                  !validation ||
                  task.revision_used
                }
              >
                {task.revision_used
                  ? "Revision used"
                  : "Request revision"}
              </button>
            </div>
          </aside>
        )}
      </div>

      {revision && (
        <div className="revision-modal">
          <div className="revision-card">
            <h2>Proposed AI revision</h2>

            <h3>{revision.eus.title}</h3>

            <p>
              {revision.eus.description}
            </p>

            <ol>
              {revision.eus.work_items.map(
                (item, index) => (
                  <li key={index}>{item}</li>
                ),
              )}
            </ol>

            <div className="revision-buttons">
              <button
                onClick={
                  handleAcceptRevision
                }
              >
                Accept revision
              </button>

              <button
                className="secondary"
                onClick={
                  handleRejectRevision
                }
              >
                Keep my current EUS
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      <footer className="task-footer">
        <span>
          Complete the EUS before submitting.
        </span>

        <button
          onClick={handleSubmit}
          disabled={loading}
        >
          Submit task
        </button>
      </footer>
    </main>
  );
}

export default App;
