export type RankedRow = {
  rank: number;
  shortlisted: boolean;
  submission: {
    submission_id: string;
    team_name: string | null;
    row_index: number;
  };
  evaluation: {
    total_score: number;
    breakdown: {
      business_impact: { score: number };
      feasibility_scalability: { score: number };
      ai_depth_creativity: { score: number };
    };
    final_summary: string;
  };
};

export type EvaluateResponse = {
  results: RankedRow[];
  count: number;
};

export type ApiError = {
  error: string;
  detail?: string;
};
