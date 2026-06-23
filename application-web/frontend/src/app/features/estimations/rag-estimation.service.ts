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

export interface RagPipelineEstimate {
  summary: string;
  estimate_markdown?: string | null;
  low_confidence: boolean;
  modules: RagEstimateModule[];
  assumptions: string[];
  sources: string[];
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
