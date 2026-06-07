import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { Observable, Subject } from 'rxjs';

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

export type OutputFormat = 'phases_table' | 'line_items' | 'narrative';

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
  output_format: OutputFormat | null;
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

export interface SessionListItem {
  session_id: string;
  project_name: string | null;
  turn_count: number;
  last_message_content: string | null;
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
  validation: StructureCheck | null;
  prompt_version: string;
  structured_result: EstimationStructuredResult | null;
  output_format: OutputFormat | null;
}

export interface SessionMessage {
  role: string;
  content: string;
}

export interface SessionProjectMetadata {
  project_name: string | null;
  assumed_team_size: number | null;
  mentioned_technologies: string[];
  agreed_scope: string | null;
}

export interface AnchorInfo {
  turn_number: number;
  anchor_type: string;
  key_information: string;
  summary: string;
}

export interface SessionStateResponse {
  session_id: string;
  project_metadata: SessionProjectMetadata;
  history: SessionMessage[];
  turn_count: number;
  message_count: number;
  anchors_count: number;
  summary_chars: number;
  last_resolved_tier: string | null;
  last_tier_rule: string | null;
  anchors: AnchorInfo[];
}

export interface CacheMetrics {
  hits: number;
  misses: number;
  total: number;
  hit_rate_pct: number;
  cost_avoided_usd: number;
  avg_latency_hit_ms: number | null;
  avg_latency_miss_ms: number | null;
  speedup_x: number | null;
  stale_reports: number;
  stale_rate_pct: number;
}

export interface RuntimeModelItem {
  effective: string;
  default: string;
  overridden: boolean;
}

export interface RuntimeModelsResponse {
  models: Record<string, RuntimeModelItem>;
  available_models: string[];
}

export type IssueSeverity = 'critical' | 'major' | 'minor';
export type IssueCategory =
  | 'arithmetic_error'
  | 'missing_component'
  | 'inconsistency_with_metadata'
  | 'internal_contradiction'
  | 'incomplete_coverage'
  | 'risk_gap';

export interface CriticIssue {
  category: IssueCategory;
  severity: IssueSeverity;
  affected_field: string;
  description: string;
}

export interface CriticFeedback {
  issues: CriticIssue[];
  overall_assessment: string;
  approved: boolean;
}

export type BossAction = 'accept' | 'iterate' | 'synthesize';

export interface BossDecision {
  action: BossAction;
  reasoning: string;
  iteration_instructions: string | null;
  synthesized_estimate: string | null;
}

export interface IterationTrace {
  iteration: number;
  candidate_estimate: string;
  critic_feedback: CriticFeedback;
  boss_decision: BossDecision;
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
  estimation_mode?: 'standard' | 'acb';
  acb_max_iterations?: number;
}

@Injectable({ providedIn: 'root' })
export class EstimationService {
  private readonly base = `${environment.apiUrl}/v1/estimations`;
  private readonly sessionsBase = `${environment.apiUrl}/v1/estimations/sessions`;
  private readonly configBase = `${this.base}/config/models`;

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

  createWithAttachmentsStream(sessionId: string, formData: FormData, promptVersion = 'v1'): Observable<string> {
    return new Observable(subscriber => {
      const url = `${this.sessionsBase}/${sessionId}/estimate?prompt_version=${promptVersion}`;
      const accessToken = localStorage.getItem('access_token');
      const headers = new Headers();

      if (accessToken) {
        headers.set('Authorization', `Bearer ${accessToken}`);
      }
      
      (async () => {
        try {
          const response = await fetch(url, {
            method: 'POST',
            body: formData,
            headers,
          });
          
          if (!response.ok) {
            // Try to parse as JSON for guardrail errors
            let error = await response.text();
            try {
              const jsonError = JSON.parse(error);
              if (jsonError.detail?.reason) {
                // It's a guardrail error - throw structured error
                subscriber.error({
                  status: response.status,
                  detail: jsonError.detail,
                });
              } else {
                subscriber.error(new Error(`HTTP ${response.status}: ${error}`));
              }
            } catch {
              // Not JSON, just plain text error
              subscriber.error(new Error(`HTTP ${response.status}: ${error}`));
            }
            return;
          }

          const reader = response.body?.getReader();
          if (!reader) {
            subscriber.error(new Error('Response body is empty'));
            return;
          }

          const decoder = new TextDecoder();
          
          const read = async () => {
            try {
              const { done, value } = await reader.read();
              if (done) {
                subscriber.complete();
                return;
              }
              
              const chunk = decoder.decode(value, { stream: true });
              subscriber.next(chunk);
              await read();
            } catch (err) {
              subscriber.error(err);
            }
          };
          
          await read();
        } catch (err) {
          subscriber.error(err);
        }
      })();
    });
  }

  getSessionState(sessionId: string) {
    return this.http.get<SessionStateResponse>(`${this.sessionsBase}/${sessionId}`);
  }

  getCacheMetrics() {
    return this.http.get<CacheMetrics>(`${this.base}/cache/metrics`);
  }

  getRuntimeModels() {
    return this.http.get<RuntimeModelsResponse>(this.configBase);
  }

  updateRuntimeModels(changes: Record<string, string | null>) {
    return this.http.put<RuntimeModelsResponse>(this.configBase, { models: changes });
  }

  listSessions() {
    return this.http.get<SessionListItem[]>(this.sessionsBase);
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
