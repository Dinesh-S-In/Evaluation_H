export type CriterionScore = {
  score: number;
  reason?: string;
};

export type SubmissionPayload = {
  submission_id: string;
  team_name: string | null;
  row_index: number;
  category_selection: string;
  category_valid?: boolean;
  category_warning?: string | null;
  key_submission_impact: string;
  business_use_case_and_impact: string;
  solution_approach_overview: string;
  tools_and_technology_used: string;
};

export type EvaluationPayload = {
  total_score: number;
  final_summary: string;
  shortlist_recommendation?: "Yes" | "No";
  model_reported_total?: number | null;
  breakdown: {
    business_impact: CriterionScore;
    feasibility_scalability: CriterionScore;
    ai_depth_creativity: CriterionScore;
  };
};

export type RankedRow = {
  rank: number;
  shortlisted: boolean;
  similarity_flag?: boolean;
  similar_submission_ids?: string[];
  submission: SubmissionPayload;
  evaluation: EvaluationPayload;
};

export type EvaluateResponse = {
  results: RankedRow[];
  count: number;
};

export type ApiError = {
  error: string;
  detail?: string;
};

export type SortKey = "rank" | "score" | "team" | "category";
