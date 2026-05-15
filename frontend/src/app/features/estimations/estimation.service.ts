import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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
  structured_result: Record<string, unknown> | null;
  requirements: string | null;
  validation_result: StructureCheck | null;
  input_tokens: number | null;
  output_tokens: number | null;
  turn_cost_usd: number | null;
  error_detail: string | null;
}

export interface EstimationCreate {
  transcription: string;
  project_id?: string;
  model?: string;
  temperature?: number;
  reasoning_effort?: 'low' | 'medium' | 'high';
  max_output_tokens?: number;
  pre_call?: boolean;
  output_format?: 'phases_table' | 'line_items' | 'narrative';
  num_examples?: number;
  prompt_version?: string;
  project_type?: string;
}

@Injectable({ providedIn: 'root' })
export class EstimationService {
  private readonly base = `${environment.apiUrl}/v1/estimations`;

  constructor(private readonly http: HttpClient) {}

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
