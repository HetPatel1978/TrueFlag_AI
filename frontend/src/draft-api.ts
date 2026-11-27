import type { AssessmentDetail } from './api';
import type { Activity, Packet, Transaction } from './investigation-api';

export type DraftRequest = {
  investigation_run_id: string;
  expected_packet_sha256: string;
  provider?: 'simulation' | 'claude';
  regulatory_query?: { query: string; limit: number };
};
export type DraftStatus = {
  draft_run_id: string;
  status:
    | 'pending'
    | 'running'
    | 'succeeded'
    | 'abstained'
    | 'failed'
    | 'invalidated';
  attempts: number;
  error_code: string | null;
  mode: 'offline_simulation' | 'claude_live';
  live_provider_used: boolean;
  human_review_required: true;
};
type FindingBase = {
  reference_id: string;
  supporting_evidence: string[];
  contradictory_evidence: string[];
};
export type DraftFinding = FindingBase &
  (
    | { claim_type: 'observed_fact'; summary: Transaction }
    | { claim_type: 'calculated_fact'; summary: Packet['facts'][number] }
    | { claim_type: 'model_signal'; summary: AssessmentDetail }
  );
export type SimulationDraft = {
  content_sha256: string;
  draft_run_id: string;
  investigation_run_id: string;
  manifest_sha256: string;
  packet_sha256: string;
  outcome: 'draft_ready' | 'abstained';
  findings: DraftFinding[];
  hypotheses: {
    question_code: string;
    supporting_evidence: string[];
    contradictory_evidence: string[];
    uncertainty: string;
  }[];
  questions: string[];
  unresolved_questions: string[];
  next_steps: string[];
  missing_evidence: string[];
  conflicts: string[];
  limitations: string[];
  provenance: {
    provider: 'deterministic_fake' | 'anthropic';
    model: 'trueflag-fake-selection.v1' | 'claude-sonnet-5-5';
    prompt_version: string;
    prompt_sha256: string;
    configuration_sha256: string;
    parent_manifest_sha256: string;
  };
  verification: 'source_reference_numeric_checks_passed';
  semantic_review: 'pending_human_review';
  regulatory_context:
    | 'unavailable_unapproved'
    | 'approved_context_human_review_required'
    | 'research_unapproved';
  regulatory_citations?: (
    | import('./investigation-api').RegulatoryPassage
    | import('./investigation-api').ResearchPassage
  )[];
  simulation: boolean;
  live_provider_used: boolean;
  /** Verified finding -> retrieved source links (new research runs only). */
  finding_citations?: {
    finding_reference_id: string;
    regulatory_citation: string;
  }[];
  retrieval?: ResearchRetrieval | null;
  /** Full hash-verified text of every retrieved section (newer research runs). */
  source_texts?: {
    reference_id: string;
    section: string;
    chunk_sha256: string;
    text: string;
  }[];
};
export type ResearchRetrieval = {
  method: string;
  inputs: string[];
  terms: string[];
  query: string;
  total_chunks: number;
  matched_chunks: number;
  passage_budget_bytes: number;
  /** v3 records: results below this fraction of the top score were dropped. */
  min_relative_score?: string;
  strong_matches?: number;
  /** v4 records: each source was sent as a bounded excerpt of its most relevant lines. */
  excerpt_cap_bytes?: number;
  /** v5 records: evidence-pattern rules that fired on the case's own transactions. */
  patterns?: { rule: string; observed: string; threshold: string }[];
  /** v5 records: inputs present in every case, left out of the query. */
  dropped_inputs?: string[];
  /** v5 records: query words with their weight (evidence-pattern words count 3). */
  weighted_terms?: { term: string; weight: number }[];
  results: {
    reference_id: string;
    rank: number;
    section: string;
    title: string;
    score: string;
    chunk_sha256: string;
    text_bytes: number;
    sent: boolean;
    excerpt_sha256?: string;
    excerpt_bytes?: number;
    excerpt_spans?: { start: number; end: number }[];
  }[];
};
export type DraftDetail = DraftStatus & { draft: SimulationDraft | null };
export type DraftHistoryItem = DraftStatus & {
  investigation_run_id: string;
  created_at: string;
  manifest_sha256: string;
  case_version: number;
  evidence_revision: number;
  access_revision: number;
  validation_status: 'stored_not_revalidated';
};
export type DraftCalculation = Activity;
