import { useEffect, useRef, useState } from "react";

import {
  acceptRevision,
  openTask,
  pauseTask,
  rejectRevision,
  requestRevision,
  resumeTask,
  saveEditor,
  startStudy,
  submitBackground,
  submitTask,
  validateEUS,
} from "./api";

import type {
  BackgroundQuestionnaire,
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

type StudyPhase =
  | "login"
  | "background"
  | "instructions"
  | "tasks"
  | "complete";

function RatingQuestion({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <fieldset className="rating-question">
      <legend>{label}</legend>

      <div className="rating-options">
        {[1, 2, 3, 4, 5].map((rating) => (
          <label key={rating}>
            <input
              type="radio"
              checked={value === rating}
              onChange={() => onChange(rating)}
            />
            {rating}
          </label>
        ))}
      </div>

      <div className="rating-labels">
        <span>Not familiar at all</span>
        <span>Very familiar</span>
      </div>
    </fieldset>
  );
}

function App() {
  const [participantId, setParticipantId] = useState(
    localStorage.getItem("participant_id") ?? "",
  );

  const [phase, setPhase] = useState<StudyPhase>("login");
  const [task, setTask] = useState<TaskView | null>(null);
  const [draft, setDraft] = useState<EUS>(EMPTY_EUS);
  const [validation, setValidation] = useState<ValidationResult | null>(null);

  const [revision, setRevision] = useState<{
    interactionId: string;
    eus: EUS;
  } | null>(null);

  const [revisionInstruction, setRevisionInstruction] = useState("");

  const [background, setBackground] = useState<BackgroundQuestionnaire>({
    primary_role: "",
    years_experience: 0,
    requirements_familiarity: 3,
    user_story_familiarity: 3,
    ethical_ai_familiarity: 3,
    generative_ai_use: "",
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      localStorage.setItem("participant_id", normalized);
      setParticipantId(normalized);

      if (state.next_task_number === null) {
        setPhase("complete");
        return;
      }

      const hasStartedTasks = state.tasks.some(
        (item) => item.status !== "not_started",
      );

      if (hasStartedTasks) {
        const nextTask = await openTask(
          normalized,
          state.next_task_number,
        );

        loadTask(nextTask);
        setPhase("tasks");
      } else if (!state.background_completed) {
        setPhase("background");
      } else {
        setPhase("instructions");
      }
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

  async function handleBackgroundSubmit() {
    if (!background.primary_role || !background.generative_ai_use) {
      setError("Please answer all questions.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await submitBackground(
        participantId,
        background,
      );

      setPhase("instructions");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not save the questionnaire.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleBeginTasks() {
    setLoading(true);
    setError(null);

    try {
      const state = await startStudy(participantId);

      if (state.next_task_number === null) {
        setPhase("complete");
        return;
      }

      const firstTask = await openTask(
        participantId,
        state.next_task_number,
      );

      loadTask(firstTask);
      setPhase("tasks");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not start the tasks.",
      );
    } finally {
      setLoading(false);
    }
  }

  function loadTask(nextTask: TaskView) {
    setTask(nextTask);
    setDraft(nextTask.current_eus ?? EMPTY_EUS);
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

      setTask((current) =>
        current
          ? {
              ...current,
              validation_used: true,
            }
          : current,
      );
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

      setTask((current) =>
        current
          ? {
              ...current,
              revision_used: true,
            }
          : current,
      );
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
    setError(null);

    try {
      const result = await acceptRevision(
        participantId,
        task.task_id,
        revision.interactionId,
      );

      setDraft(result.current_eus);
      setRevision(null);

      /*
       * The validation refers to the EUS before the revision was accepted,
       * so it should no longer be displayed as feedback about the current EUS.
       */
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
    setError(null);

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
        setPhase("complete");
        return;
      }

      const nextTaskNumber = task.task_number + 1;

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

    const currentTask = task;

    async function handleVisibilityChange() {
      if (document.hidden) {
        inactiveStartedAt.current = Date.now();

        try {
          await pauseTask(
            participantId,
            currentTask.task_id,
          );
        } catch {
          return;
        }
      } else if (inactiveStartedAt.current !== null) {
        inactiveSeconds.current +=
          (Date.now() - inactiveStartedAt.current) / 1000;

        inactiveStartedAt.current = null;

        try {
          await resumeTask(
            participantId,
            currentTask.task_id,
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

  if (phase === "login") {
    return (
      <main className="start-page">
        <div className="start-card">
          <h1>EAI-USG Study</h1>

          <p>
            Enter the participant ID provided by the researcher to begin
            or continue the study.
          </p>

          <input
            value={participantId}
            onChange={(event) =>
              setParticipantId(event.target.value)
            }
            placeholder="Participant ID"
          />

          <button
            onClick={handleStart}
            disabled={loading}
          >
            {loading ? "Loading..." : "Continue"}
          </button>

          {error && (
            <p className="error">{error}</p>
          )}
        </div>
      </main>
    );
  }

  if (phase === "background") {
    return (
      <main className="start-page">
        <div className="instructions-card">
          <h1>Background questionnaire</h1>

          <p>
            Before beginning the tasks, please answer a few questions about
            your professional background and prior experience.
          </p>

          <label>
            Primary role
            <select
              value={background.primary_role}
              onChange={(event) =>
                setBackground({
                  ...background,
                  primary_role: event.target.value,
                })
              }
            >
              <option value="">Select an option</option>
              <option value="software_developer">
                Software Developer / Engineer
              </option>
              <option value="requirements_analyst">
                Requirements / Business Analyst
              </option>
              <option value="tester">
                Tester / QA
              </option>
              <option value="architect">
                Software Architect
              </option>
              <option value="researcher">
                Researcher
              </option>
              <option value="student">
                Student
              </option>
              <option value="other">
                Other
              </option>
            </select>
          </label>

          <label>
            Years of experience in software development or software engineering
            <input
              type="number"
              min="0"
              step="0.5"
              value={background.years_experience}
              onChange={(event) =>
                setBackground({
                  ...background,
                  years_experience: Number(event.target.value),
                })
              }
            />
          </label>

          <RatingQuestion
            label="How familiar are you with requirements engineering?"
            value={background.requirements_familiarity}
            onChange={(value) =>
              setBackground({
                ...background,
                requirements_familiarity: value,
              })
            }
          />

          <RatingQuestion
            label="How familiar are you with user stories?"
            value={background.user_story_familiarity}
            onChange={(value) =>
              setBackground({
                ...background,
                user_story_familiarity: value,
              })
            }
          />

          <RatingQuestion
            label="How familiar are you with ethical or responsible AI?"
            value={background.ethical_ai_familiarity}
            onChange={(value) =>
              setBackground({
                ...background,
                ethical_ai_familiarity: value,
              })
            }
          />

          <label>
            How often do you use generative AI tools for software engineering
            activities?
            <select
              value={background.generative_ai_use}
              onChange={(event) =>
                setBackground({
                  ...background,
                  generative_ai_use: event.target.value,
                })
              }
            >
              <option value="">Select an option</option>
              <option value="never">Never</option>
              <option value="rarely">Rarely</option>
              <option value="monthly">Monthly</option>
              <option value="weekly">Weekly</option>
              <option value="daily">Daily</option>
            </select>
          </label>

          {error && (
            <p className="error">{error}</p>
          )}

          <button
            onClick={handleBackgroundSubmit}
            disabled={loading}
          >
            {loading ? "Saving..." : "Continue"}
          </button>
        </div>
      </main>
    );
  }

  if (phase === "instructions") {
    return (
      <main className="start-page">
        <div className="instructions-card">
          <h1>Study instructions</h1>

          <p>
            In this study, you will complete six tasks involving the authoring
            of Ethical User Stories from given ethical requirements.
          </p>

          <h2>Ethical User Story format</h2>

          <p>
            For each task, you will produce an Ethical User Story with:
          </p>

          <ul>
            <li>
              <strong>Title:</strong> a concise name for the ethical requirement
              being operationalized.
            </li>
            <li>
              <strong>Description:</strong> a user-story-style description
              expressing the ethical objective.
            </li>
            <li>
              <strong>Work items:</strong> concrete development activities that
              operationalize the requirement.
            </li>
          </ul>

          <h2>Task conditions</h2>

          <p>
            Some tasks will use structured manual authoring. In these tasks,
            you will create the Ethical User Story yourself from a blank editor.
          </p>

          <p>
            Other tasks will provide EAI-USG support. These tasks begin with an
            AI-generated Ethical User Story that you may inspect, edit, or replace
            as you see fit. Additional AI support may also be available during
            the task.
          </p>

          <h2>During the study</h2>

          <ul>
            <li>
              Read the ethical requirement carefully before authoring.
            </li>
            <li>
              You may freely modify the title, description, and work items.
            </li>
            <li>
              In EAI-USG-assisted tasks, using the additional AI support is optional.
            </li>
            <li>
              Submit the artifact only when you consider the Ethical User Story finished.
            </li>
            <li>
              Please do not use external AI assistants while completing the tasks.
            </li>
          </ul>

          <p className="instructions-note">
            The study records task timing and interactions with the study interface
            for research purposes.
          </p>

          {error && (
            <p className="error">{error}</p>
          )}

          <button
            onClick={handleBeginTasks}
            disabled={loading}
          >
            {loading ? "Starting..." : "Start tasks"}
          </button>
        </div>
      </main>
    );
  }

  if (phase === "complete") {
    return (
      <main className="start-page">
        <div className="start-card">
          <h1>Study completed</h1>

          <p>
            Thank you for participating. Your responses have been recorded.
          </p>
        </div>
      </main>
    );
  }

  if (phase !== "tasks" || !task) {
    return null;
  }

  const assisted = task.condition === "eai_usg";

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
                    description: event.target.value,
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
                    disabled={draft.work_items.length === 1}
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
                <summary>Initial traceability</summary>

                <h3>Source obligations</h3>

                {task.initial_traceability.analysis.obligations.map(
                  (obligation) => (
                    <div
                      className="obligation"
                      key={obligation.id}
                    >
                      <strong>{obligation.id}</strong>
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
                        Item {trace.work_item_index + 1}: {" "}
                        {trace.obligation_ids.join(", ") ||
                          "No obligation links"}
                      </strong>

                      <p>{trace.explanation}</p>
                    </div>
                  ),
                )}
              </details>
            )}

            <div className="ai-action">
              <h3>Validation</h3>

              <button
                onClick={handleValidation}
                disabled={loading || task.validation_used}
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
                  <span>Clarity {validation.clarity}/5</span>
                  <span>Completeness {validation.completeness}/5</span>
                  <span>Actionability {validation.actionability}/5</span>
                  <span>Testability {validation.testability}/5</span>
                  <span>Faithfulness {validation.faithfulness}/5</span>
                </div>

                {validation.issues.length > 0 ? (
                  validation.issues.map(
                    (issue, index) => (
                      <div
                        className="issue"
                        key={index}
                      >
                        <strong>
                          {issue.dimension} — {issue.severity}
                        </strong>

                        <p>{issue.problem}</p>

                        <small>
                          Revision objective: {issue.recommended_change}
                        </small>
                      </div>
                    ),
                  )
                ) : (
                  <p>No substantive issues identified.</p>
                )}
              </div>
            )}

            <div className="ai-action">
              <h3>AI revision</h3>

              <textarea
                placeholder="Optional revision instruction"
                value={revisionInstruction}
                onChange={(event) =>
                  setRevisionInstruction(event.target.value)
                }
                disabled={!validation || task.revision_used}
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
            <p>{revision.eus.description}</p>

            <ol>
              {revision.eus.work_items.map(
                (item, index) => (
                  <li key={index}>{item}</li>
                ),
              )}
            </ol>

            <div className="revision-buttons">
              <button onClick={handleAcceptRevision}>
                Accept revision
              </button>

              <button
                className="secondary"
                onClick={handleRejectRevision}
              >
                Keep my current EUS
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="error-banner">{error}</div>
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
