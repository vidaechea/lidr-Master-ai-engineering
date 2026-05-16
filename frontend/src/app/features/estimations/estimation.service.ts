import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export type EstimationStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type GuardrailReason = 'pii' | 'prompt_injection' | 'moderation';

export interface GuardrailError {
  message: string;
  reason: GuardrailReason;
}

export interface StructureCheck {
  has_title: boolean;
  has_breakdown_table: boolean;
  has_totals_section: boolean;
  has_team_section: boolean;
  has_duration_section: boolean;
  declared_total_hours: number | null;
  sum_row_hours: number | null;
  hours_match: boolean | null;
  declared_total_cost: number | null;
  sum_row_cost: number | null;
  cost_match: boolean | null;
  finish_reason_ok: boolean;
  score: number;
  issues: string[];
}

export interface EstimationPhase {
  name: string;
  duration_weeks: number;
  cost_eur: number;
  confidence_pct: number;
  summary: string | null;
  assumptions: string[];
}

export interface EstimationStructuredResult {
  summary: string;
  total_duration_weeks: number;
  total_cost_eur: number;
  confidence_pct: number;
  phases: EstimationPhase[];
}

export interface EstimationListItem {
  id: string;
  project_id: string | null;
  status: EstimationStatus;
  model_used: string | null;
  total_cost_usd: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface EstimationOut extends EstimationListItem {
  transcription: string;
  prompt_version: string | null;
  estimation_markdown: string | null;
  structured_result: EstimationStructuredResult | null;
  requirements: string | null;
  validation_result: StructureCheck | null;
  input_tokens: number | null;
  output_tokens: number | null;
  turn_cost_usd: number | null;
  error_detail: string | null;
}

export interface ReferenceProject {
  name: string;
  description: string;
  total_hours: number | null;
  total_cost: number | null;
}

export interface SessionCreateResponse {
  session_id: string;
}

export interface SessionEstimationResponse {
  estimation: string;
  model: string;
  response_id: string | null;
  input_tokens: number;
  output_tokens: number;
  turn_cost_usd: number;
  total_cost_usd: number;
  estimated_input_tokens: number;
  estimated_precall_cost_usd: number | null;
  requirements: string | null;
  pre_call_cost_usd: number | null;
  prompt_version: string;
}

export interface EstimationCreate {
  transcription: string;
  project_id?: string;
  model?: string;
  temperature?: number;
  top_p?: number;
  reasoning_effort?: 'low' | 'medium' | 'high';
  max_output_tokens?: number;
  pre_call?: boolean;
  output_format?: 'phases_table' | 'line_items' | 'narrative';
  example_format?: 'markdown' | 'json' | 'narrative';
  num_examples?: number;
  prompt_version?: string;
  project_type?: 'mobile_app' | 'web_saas' | 'internal_tool' | 'data_pipeline';
  detail_level?: 'summary' | 'medium' | 'detailed';
  reference_projects?: ReferenceProject[];
}

@Injectable({ providedIn: 'root' })
export class EstimationService {
  private readonly base = `${environment.apiUrl}/v1/estimations`;
  private readonly sessionsBase = `${environment.aiEngineApiUrl}/api/v1/sessions`;

  constructor(private readonly http: HttpClient) {}

  createSession() {
    return this.http.post<SessionCreateResponse>(this.sessionsBase, {});
  }

  createWithAttachments(sessionId: string, formData: FormData, promptVersion = 'v1') {
    const params = new HttpParams().set('prompt_version', promptVersion);
    return this.http.post<SessionEstimationResponse>(
      `${this.sessionsBase}/${sessionId}/estimate`,
      formData,
      { params },
    );
  }

  list(projectId?: string) {
    const params: Record<string, string> = {};
    if (projectId) params['project_id'] = projectId;
    return this.http.get<EstimationListItem[]>(this.base, { params });
  }

  get(id: string) {
    return this.http.get<EstimationOut>(`${this.base}/${id}`);
  }

  create(data: EstimationCreate) {
    return this.http.post<EstimationOut>(this.base, data);
  }

  createAsync(data: EstimationCreate) {
    return this.http.post<{ estimation_id: string; job_id: string; status: string }>(
      `${this.base}/async`, data
    );
  }

  pollStatus(id: string) {
    return this.http.get<{ id: string; status: EstimationStatus; completed_at: string | null }>(
      `${this.base}/${id}/status`
    );
  }
}
