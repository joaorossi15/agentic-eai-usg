export type StudyCondition = "manual" | "eai_usg";

export interface EUS {
  title: string;
  description: string;
  work_items: string[];
}

export interface Requirement {
  id: string;
  text: string;
}

export interface Obligation {
  id: string;
  text: string;
  source_span: string;
  support_type: "explicit" | "reasonable_implication";
}

export interface RequirementAnalysis {
  ethical_objective: string;
  stakeholders: string[];
  obligations: Obligation[];
  constraints: string[];
  ambiguities: string[];
  unsupported_assumptions_to_avoid: string[];
  possible_operational_aspects: string[];
}

export interface WorkItemTrace {
  work_item_index: number;
  obligation_ids: string[];
  explanation: string;
}

export interface TraceabilityMap {
  description_obligation_ids: string[];
  work_items: WorkItemTrace[];
}

export interface TraceabilityResult {
  analysis: RequirementAnalysis;
  traceability: TraceabilityMap;
}

export interface BackgroundQuestionnaire {
  primary_role: string;
  years_experience: number;
  requirements_familiarity: number;
  user_story_familiarity: number;
  ethical_ai_familiarity: number;
  generative_ai_use: string;
}

export interface QualityIssue {
  dimension:
    | "clarity"
    | "completeness"
    | "actionability"
    | "testability"
    | "faithfulness";
  severity: "minor" | "major";
  problem: string;
  recommended_change: string;
}

export interface ValidationResult {
  clarity: number;
  completeness: number;
  actionability: number;
  testability: number;
  faithfulness: number;
  issues: QualityIssue[];
}

export interface RevisionState {
  interaction_id: string;
  instruction: string | null;
  output: EUS;
  decision: "accepted" | "rejected" | null;
}

export interface TaskView {
  task_id: string;
  task_number: number;
  requirement: Requirement;
  principle: string;
  condition: StudyCondition;
  status: "not_started" | "in_progress" | "completed";
  initial_eus: EUS | null;
  initial_traceability: TraceabilityResult | null;
  current_eus: EUS | null;
  final_eus: EUS | null;
  validation: ValidationResult | null;
  revision: RevisionState | null;
  validation_used: boolean;
  revision_used: boolean;
}

export interface StudyTaskSummary {
  task_id: string;
  task_number: number;
  requirement_id: string;
  principle: string;
  condition: StudyCondition;
  status: "not_started" | "in_progress" | "completed";
}

export interface StudyState {
  participant_id: string;
  status: "not_started" | "in_progress" | "completed" | "withdrawn";
  started_at: string | null;
  completed_at: string | null;
  background_completed: boolean;
  next_task_number: number | null;
  tasks: StudyTaskSummary[];
}
