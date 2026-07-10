import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { Observable } from 'rxjs';

/**
 * RAG Pipeline Estimation Types
 */

export interface RagEstimateTask {
  name: string;
  engineer_days: number;
}

export interface RagEstimateModule {
  name: string;
  engineer_days: number;
  tasks: RagEstimateTask[];
}

export interface RagSourceReference {
  chunk_id: string;
  document_id: string;
  evidence: string;
}

export interface RagEstimateLineItem {
  component: string;
  hours: number;
  rationale: string;
  grounded: boolean;
  sources: RagSourceReference[];
}

export interface RagPipelineEstimate {
  summary: string;
  estimate_markdown?: string | null;
  low_confidence: boolean;
  modules: RagEstimateModule[];
  line_items: RagEstimateLineItem[];
  assumptions: string[];
  sources: string[];
}

export interface HallucinationLineReport {
  component: string;
  status: 'grounded' | 'degraded' | 'insufficient_context';
  estimated_hours?: number | null;
  anchored_hours: number[];
  cited_chunk_ids: string[];
  reason: string;
}

export interface HallucinationReport {
  total_lines: number;
  grounded_lines: number;
  degraded_lines: number;
  insufficient_lines: number;
  lines: HallucinationLineReport[];
}

export interface TaskNeighbor {
  source_id: string;
  budget_id?: string | null;
  estimated_hours: number;
  distance: number;
}

export interface HourRange {
  min_hours: number;
  max_hours: number;
  reason: string;
}

export interface TaskHoursEstimate {
  module: string;
  task: string;
  estimated_hours?: number | null;
  reliability?: number | null;
  has_match: boolean;
  dispersion?: number | null;
  neighbors: TaskNeighbor[];
  hours_range?: HourRange | null;
}

export interface TaskHoursResult {
  tasks: TaskHoursEstimate[];
  agent_trace?: AgentTrace | null;
}

export interface AgentTraceStep {
  step: number;
  reasoning_summary?: string | null;
  tool: string;
  tool_args: Record<string, any>;
  observation: string;
}

export interface AgentTrace {
  steps: AgentTraceStep[];
}

export type AgentReasoningEffort = 'minimal' | 'low' | 'medium' | 'high';

export interface AgentProfileConfig {
  model?: string | null;
  reasoning_effort?: AgentReasoningEffort | null;
  max_iterations?: number | null;
  search_top_k?: number | null;
  search_distance_threshold?: number | null;
}

export interface AgentProfile {
  id: string;
  name: string;
  persona?: string | null;
  config: AgentProfileConfig;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentProfileCreate {
  name: string;
  persona?: string | null;
  config: AgentProfileConfig;
  is_default: boolean;
}

export interface AgentStructureRequest {
  query: {
    search_text: string;
    sector?: string | null;
    year_from?: number | null;
    year_to?: number | null;
    chunk_types: string[];
    keywords: string[];
  };
  profile_id?: string;
}

export interface AgentStructureResponse {
  estimate: RagPipelineEstimate;
  agent_trace?: AgentTrace | null;
}

export interface AgentHoursRequest {
  modules: TaskHoursModuleInput[];
  profile_id?: string;
}

export interface RetrievedChunk {
  source_id: string;
  chunk_id: number;
  document_id: number;
  chunk_type: string;
  content: string;
  distance: number;
  metadata: Record<string, any>;
}

export interface RetrievalResult {
  query: string;
  top_k: number;
  candidates_evaluated: number;
  low_confidence: boolean;
  chunks: RetrievedChunk[];
}

export interface ReformulationStageOut {
  search_text: string;
  sector: string | null;
  year_from: number | null;
  year_to: number | null;
  chunk_types: string[];
  keywords: string[];
  used_fallback: boolean;
}

export interface AssemblyResult {
  context_block: string;
  included_source_ids: string[];
  token_count_estimate: number;
  truncated: boolean;
}

export interface FullRagEstimationResponse {
  request_id: string | null;
  reformulation: ReformulationStageOut;
  retrieval: { retrieval: RetrievalResult };
  assembly: AssemblyResult;
  generation: { estimate: RagPipelineEstimate };
  idempotency_hit: boolean;
  processing_time_ms?: number;
}

export interface RagEstimationRequest {
  transcript: string;
  top_k?: number;
  distance_threshold?: number;
  idempotency_key?: string;
}

export interface RagEstimationListItem {
  id: string;
  transcript: string;
  summary: string;
  confidence: 'high' | 'low';
  modules_count: number;
  created_at: string;
  status: 'completed' | 'failed' | 'pending';
}

export interface RagVerifyRequest {
  estimate: RagPipelineEstimate;
  kept_chunks: RetrievedChunk[];
  use_judge?: boolean;
}

export interface TaskHoursTaskInput {
  name: string;
  description?: string;
}

export interface TaskHoursModuleInput {
  name: string;
  tasks: TaskHoursTaskInput[];
}

export interface RagTaskHoursRequest {
  modules: TaskHoursModuleInput[];
}

export interface RagIndexRunRequest {
  documents: Record<string, any>[];
  document_type?: string;
  chunk_type?: string;
}

export interface RagIndexRunResponse {
  job_id: string;
  documents_total: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface RagIndexJob {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  documents_processed: number;
  error_message?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface RagCollectionStats {
  collection: string;
  documents: number;
  chunks: number;
  hnsw_indexed: boolean;
}

export interface RagIndexStats {
  collections: RagCollectionStats[];
  total_chunks: number;
}

@Injectable({
  providedIn: 'root',
})
export class RagEstimationService {
  private readonly baseUrl = `${environment.apiUrl}/v1/rag`;

  constructor(private readonly http: HttpClient) {}

  /**
   * Create a new RAG pipeline estimation
   * Full orchestration: reformulation → retrieval → assembly → generation
   */
  createEstimation(request: RagEstimationRequest): Observable<FullRagEstimationResponse> {
    return this.http.post<FullRagEstimationResponse>(`${this.baseUrl}/estimate`, request);
  }

  /**
   * Retrieve a single RAG estimation by ID
   */
  getEstimation(estimationId: string): Observable<FullRagEstimationResponse> {
    return this.http.get<FullRagEstimationResponse>(
      `${this.baseUrl}/estimates/${estimationId}`
    );
  }

  /**
   * Verify grounded line items against cited chunk evidence
   */
  verifyStage(request: RagVerifyRequest): Observable<HallucinationReport> {
    return this.http.post<HallucinationReport>(`${this.baseUrl}/stages/verify`, request);
  }

  /**
   * Estimate per-task hours from historical RAG matches
   */
  estimateTaskHours(request: RagTaskHoursRequest): Observable<TaskHoursResult> {
    return this.http.post<TaskHoursResult>(`${this.baseUrl}/tasks/hours`, request);
  }

  proposeAgentStructure(request: AgentStructureRequest): Observable<AgentStructureResponse> {
    return this.http.post<AgentStructureResponse>(`${this.baseUrl}/agent/structure`, request);
  }

  estimateAgentHours(request: AgentHoursRequest): Observable<TaskHoursResult> {
    return this.http.post<TaskHoursResult>(`${this.baseUrl}/agent/hours`, request);
  }

  listAgentProfiles(): Observable<AgentProfile[]> {
    return this.http.get<AgentProfile[]>(`${this.baseUrl}/agent/profiles`);
  }

  createAgentProfile(request: AgentProfileCreate): Observable<AgentProfile> {
    return this.http.post<AgentProfile>(`${this.baseUrl}/agent/profiles`, request);
  }

  updateAgentProfile(profileId: string, request: Partial<AgentProfileCreate>): Observable<AgentProfile> {
    return this.http.patch<AgentProfile>(`${this.baseUrl}/agent/profiles/${profileId}`, request);
  }

  deleteAgentProfile(profileId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/agent/profiles/${profileId}`);
  }

  /**
   * Start a corpus index expansion run
   */
  createIndexRun(request: RagIndexRunRequest): Observable<RagIndexRunResponse> {
    return this.http.post<RagIndexRunResponse>(`${this.baseUrl}/index/runs`, request);
  }

  /**
   * Poll corpus index job status
   */
  getIndexJob(jobId: string): Observable<RagIndexJob> {
    return this.http.get<RagIndexJob>(`${this.baseUrl}/index/jobs/${jobId}`);
  }

  /**
   * Read corpus index aggregate stats
   */
  getIndexStats(): Observable<RagIndexStats> {
    return this.http.get<RagIndexStats>(`${this.baseUrl}/index/stats`);
  }

  /**
   * List RAG estimations with optional filters
   */
  listEstimations(params?: {
    project_id?: string;
    status?: 'completed' | 'failed' | 'pending';
    limit?: number;
    offset?: number;
  }): Observable<RagEstimationListItem[]> {
    let httpParams = new HttpParams();

    if (params) {
      if (params.project_id) httpParams = httpParams.set('project_id', params.project_id);
      if (params.status) httpParams = httpParams.set('status', params.status);
      if (params.limit) httpParams = httpParams.set('limit', params.limit.toString());
      if (params.offset) httpParams = httpParams.set('offset', params.offset.toString());
    }

    return this.http.get<RagEstimationListItem[]>(`${this.baseUrl}/estimates`, {
      params: httpParams,
    });
  }

  /**
   * Format engineer_days as readable string (e.g., "5.0 days")
   */
  formatEngineerDays(days: number): string {
    if (days < 1) {
      const hours = Math.round(days * 8);
      return `${hours}h`;
    }
    return `${days.toFixed(1)} days`;
  }

  /**
   * Calculate total engineer days from modules
   */
  calculateTotalDays(modules: RagEstimateModule[]): number {
    return modules.reduce((total, module) => {
      const moduleDays = module.engineer_days + module.tasks.reduce((sum, task) => sum + task.engineer_days, 0);
      return total + moduleDays;
    }, 0);
  }

  /**
   * Format confidence level
   */
  formatConfidence(lowConfidence: boolean): string {
    return lowConfidence ? 'Low' : 'High';
  }

  /**
   * Get confidence CSS class for styling
   */
  getConfidenceClass(lowConfidence: boolean): string {
    return lowConfidence ? 'confidence-low' : 'confidence-high';
  }
}
