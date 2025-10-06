export type NoteState = "draft" | "needs_review" | "approved";

export type ReviewStatus = "open" | "changes_requested" | "merged" | "closed";

export type ReviewDecision = "approved" | "changes_requested" | "commented";

export type NoteResponse = {
  id: string;
  title: string;
  created_by: string;
  committed_by?: string | null;
  tags: string[];
  state: NoteState;
  version_id: string;
  version_index: number;
  content: string;
  submitted_by?: string | null;
  reviewed_by?: string | null;
  review_comment?: string | null;
  created_at: string;
  upvotes: number;
  downvotes: number;
  has_draft?: boolean;
  active_review_id?: string | null;
  active_review_status?: ReviewStatus | null;
  deleted_at?: string | null;
  deleted_by?: string | null;
};

export type ReviewDecisionResponse = {
  user_id: string;
  decision: ReviewDecision;
  comment?: string | null;
  updated_at: string;
};

export type ReviewInfo = {
  id: string;
  note_id: string;
  draft_version_id: string;
  base_version_id?: string | null;
  title: string;
  description?: string | null;
  created_by: string;
  reviewer_ids: string[];
  status: ReviewStatus;
  created_at: string;
  updated_at: string;
  merged_at?: string | null;
  merged_by?: string | null;
  closed_at?: string | null;
  merge_version_id?: string | null;
  type?: string | null;
  approvals_count: number;
  change_requests_count: number;
  decisions: ReviewDecisionResponse[];
};

export type ReviewSubmissionResponse = {
  version: NoteResponse;
  review: ReviewInfo;
};

export type ReviewEventResponse = {
  id: string;
  event_type: string;
  author_id: string;
  message?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ReviewSummary = {
  review: ReviewInfo;
  draft_version: NoteResponse;
  base_version?: NoteResponse | null;
};

export type ReviewDetailResponse = {
  review: ReviewInfo;
  draft_version: NoteResponse;
  base_version?: NoteResponse | null;
  events: ReviewEventResponse[];
};

export type ReviewMergeResponse = {
  review: ReviewInfo;
  version: NoteResponse;
};

export type SearchResult = {
  version: NoteResponse;
  score: number;
};

export type SearchResponse = {
  items: SearchResult[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type NotesStats = {
  total_notes: number;
  total_versions: number;
  approved_versions: number;
  draft_versions: number;
  needs_review_versions: number;
  distinct_tags: number;
  active_authors: number;
};
