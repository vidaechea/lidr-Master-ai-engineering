import { Component, OnInit, computed, signal } from '@angular/core';
import { JsonPipe, TitleCasePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { switchMap } from 'rxjs';
import { EstimationResultComponent } from '../estimation-result/estimation-result.component';
import {
  CacheMetrics,
  EstimationCreate,
  EstimationService,
  GuardrailError,
  GuardrailReason,
  ReferenceProject,
  SessionProjectMetadata,
  SessionEstimationResponse,
} from '../estimation.service';

const GUARDRAIL_ICONS: Record<GuardrailReason, string> = {
  pii: 'person_off',
  prompt_injection: 'security',
  moderation: 'block',
};

@Component({
  selector: 'app-estimation-form',
  standalone: true,
  imports: [
    FormsModule,
    JsonPipe,
    TitleCasePipe,
    MatExpansionModule,
    MatIconModule,
    MatProgressSpinnerModule,
    EstimationResultComponent,
  ],
  template: `
    <div class="page">
      <div class="chat-container">
        <!-- Header with session info -->
        <div class="chat-header">
          <div class="header-left">
            <h2 class="head-title">{{ isExistingSession() ? 'Estimation' : 'New Estimation' }}</h2>
            <p class="head-sub">Session: {{ sessionId() ?? 'creating...' }}</p>
          </div>
          <button type="button" class="btn-secondary" (click)="startNewConversation()" [disabled]="loading()">
            <mat-icon>add_comment</mat-icon>
            <span>Nueva conversación</span>
          </button>
          <!-- Sidebar toggle -->
          <button type="button" class="btn-sidebar-toggle" 
            [class.active]="sidebarOpen()"
            (click)="toggleSidebar()"
            title="Toggle metadata sidebar">
            <mat-icon>{{ sidebarOpen() ? 'close' : 'info' }}</mat-icon>
          </button>
        </div>

        <!-- Main layout with sidebar -->
        <div class="layout-wrapper">
          <!-- Sidebar -->
          @if (sidebarOpen()) {
            <div class="sidebar">
              <div class="sidebar-header">
                <h3>Project Metadata</h3>
                <span class="sidebar-hint">Debugging view</span>
              </div>
              <div class="sidebar-content">
                @if (projectMetadata(); as metadata) {
                  <div class="metadata-section">
                    <div class="metadata-label">Session ID</div>
                    <div class="metadata-value session-id">{{ sessionId() ?? 'N/A' }}</div>
                  </div>
                  
                  <div class="metadata-section">
                    <div class="metadata-label">Turn Count</div>
                    <div class="metadata-value">{{ turnCount() }}</div>
                  </div>
                  
                  <div class="metadata-section">
                    <div class="metadata-label">History Messages</div>
                    <div class="metadata-value">{{ historyMessageCount() }}</div>
                  </div>

                  <div class="metadata-section">
                    <div class="metadata-label metadata-label-row">
                      <span>Cache Metrics</span>
                      <button type="button" class="btn-cache-refresh" (click)="refreshCacheMetrics()">
                        <mat-icon>refresh</mat-icon>
                      </button>
                    </div>
                    @if (cacheMetricsLoading()) {
                      <div class="metadata-value">Loading cache metrics...</div>
                    } @else if (cacheMetricsError()) {
                      <div class="metadata-value metadata-value-error">{{ cacheMetricsError() }}</div>
                    } @else if (cacheMetrics(); as metrics) {
                      <div class="metrics-grid">
                        <div class="metric-card">
                          <div class="metric-k">Hit rate</div>
                          <div class="metric-v">{{ metrics.hit_rate_pct }}%</div>
                        </div>
                        <div class="metric-card">
                          <div class="metric-k">Hits</div>
                          <div class="metric-v">{{ metrics.hits }}</div>
                        </div>
                        <div class="metric-card">
                          <div class="metric-k">Misses</div>
                          <div class="metric-v">{{ metrics.misses }}</div>
                        </div>
                        <div class="metric-card">
                          <div class="metric-k">Cost avoided</div>
                          <div class="metric-v">{{ formatCost(metrics.cost_avoided_usd) }}</div>
                        </div>
                        <div class="metric-card">
                          <div class="metric-k">Speedup</div>
                          <div class="metric-v">{{ metrics.speedup_x ?? 'N/A' }}x</div>
                        </div>
                        <div class="metric-card">
                          <div class="metric-k">Stale reports</div>
                          <div class="metric-v">{{ metrics.stale_reports }}</div>
                        </div>
                      </div>
                    } @else {
                      <div class="metadata-value">No cache metrics yet.</div>
                    }
                  </div>

                  @if (metadata.project_name) {
                    <div class="metadata-section">
                      <div class="metadata-label">Project Name</div>
                      <div class="metadata-value">{{ metadata.project_name }}</div>
                    </div>
                  }

                  @if (metadata.assumed_team_size) {
                    <div class="metadata-section">
                      <div class="metadata-label">Team Size</div>
                      <div class="metadata-value">{{ metadata.assumed_team_size }} people</div>
                    </div>
                  }

                  @if (metadata.mentioned_technologies && metadata.mentioned_technologies.length > 0) {
                    <div class="metadata-section">
                      <div class="metadata-label">Technologies</div>
                      <div class="metadata-value">
                        <ul class="req-list">
                          @for (tech of metadata.mentioned_technologies; track $index) {
                            <li>{{ tech }}</li>
                          }
                        </ul>
                      </div>
                    </div>
                  }

                  @if (metadata.agreed_scope) {
                    <div class="metadata-section">
                      <div class="metadata-label">Agreed Scope</div>
                      <div class="metadata-value">{{ metadata.agreed_scope }}</div>
                    </div>
                  }

                  <div class="metadata-section">
                    <div class="metadata-label">Full JSON</div>
                    <pre class="metadata-json-full">{{ metadata | json }}</pre>
                  </div>
                } @else {
                  <div class="metadata-empty">No metadata yet for this session.</div>
                }
              </div>
            </div>
          }

          <!-- Main chat area with tabs -->
          <div class="chat-area">
            <!-- Tabs header -->
            <div class="tabs-header">
              <button 
                type="button" 
                class="tab-button"
                [class.tab-active]="activeTab() === 'form'"
                (click)="activeTab.set('form')">
                <mat-icon>description</mat-icon>
                <span>Formulario</span>
              </button>
              <button 
                type="button" 
                class="tab-button"
                [class.tab-active]="activeTab() === 'response'"
                (click)="activeTab.set('response')">
                <mat-icon>{{ isStreaming() ? 'schedule' : 'check_circle' }}</mat-icon>
                <span>Respuesta</span>
                @if (isStreaming() || streamingResult()) {
                  <span class="tab-badge">●</span>
                }
              </button>
            </div>

            <!-- Tabs content -->
            <div class="tabs-content">
              <!-- Form Tab -->
              @if (activeTab() === 'form') {
                <div class="tab-pane">
            <form (ngSubmit)="submit()" class="chat-form">
              <!-- Transcript textarea -->
              <div class="field">
                <label class="field-label" for="transcription">
                  Transcript / Description <span class="required">*</span>
                </label>
                <textarea id="transcription" class="textarea" name="transcription"
                  [(ngModel)]="form.transcription"
                  rows="6" maxlength="20000" required minlength="20"
                  placeholder="Paste meeting transcript or project description here...">
                </textarea>
                <div class="textarea-footer">
                  <span class="char-count">{{ form.transcription.length }} / 20,000</span>
                </div>
              </div>

              <!-- Attachments -->
              <div class="field">
                <label class="field-label">
                  Attachments <em class="optional-tag">(optional)</em>
                </label>
                <div class="attach-zone" [class.attach-zone--drag]="dragOver()"
                  (dragover)="onDragOver($event)" (dragleave)="onDragLeave($event)" (drop)="onDrop($event)"
                  (click)="fileInput.click()" (keydown.enter)="fileInput.click()" tabindex="0" role="button"
                  aria-label="Upload attachments">
                  <input #fileInput type="file" accept=".pdf,.docx,.txt" multiple hidden
                    (change)="onFilesSelected($event)">
                  <mat-icon class="attach-icon">cloud_upload</mat-icon>
                  <span class="attach-label">Drop files or <strong>click</strong></span>
                </div>
                @if (attachments().length > 0) {
                  <div class="file-list">
                    @for (f of attachments(); track $index; let i = $index) {
                      <div class="file-chip">
                        <mat-icon class="file-icon">{{ fileIcon(f) }}</mat-icon>
                        <span class="file-name">{{ f.name }}</span>
                        <button type="button" class="file-remove" (click)="removeAttachment(i)">
                          <mat-icon>close</mat-icon>
                        </button>
                      </div>
                    }
                  </div>
                }
              </div>

              <!-- Options row -->
              <!-- Primary row: Project type / Output format / Detail level -->
              <div class="selects-row">
                <div class="select-group">
                  <label class="select-label"><mat-icon class="select-icon">category</mat-icon> Project type</label>
                  <div class="select-wrap">
                    <select class="select" name="projectType" [(ngModel)]="form.project_type">
                      <option value="">None</option>
                      <option value="mobile_app">Mobile App</option>
                      <option value="web_saas">Web SaaS</option>
                      <option value="internal_tool">Internal Tool</option>
                      <option value="data_pipeline">Data Pipeline</option>
                    </select>
                    <mat-icon class="chevron">expand_more</mat-icon>
                  </div>
                </div>
                <div class="select-group">
                  <label class="select-label">
                    <mat-icon class="select-icon">table_chart</mat-icon> Output format
                  </label>
                  <div class="select-wrap">
                    <select class="select" name="outputFormat" [(ngModel)]="form.output_format">
                      <option value="phases_table">Phases table</option>
                      <option value="line_items">Line items</option>
                      <option value="narrative">Narrative</option>
                    </select>
                    <mat-icon class="chevron">expand_more</mat-icon>
                  </div>
                </div>
                <div class="select-group">
                  <label class="select-label"><mat-icon class="select-icon">tune</mat-icon> Detail level</label>
                  <div class="select-wrap">
                    <select class="select" name="detailLevel" [(ngModel)]="form.detail_level">
                      <option value="">Default</option>
                      <option value="summary">Summary</option>
                      <option value="medium">Medium</option>
                      <option value="detailed">Detailed</option>
                    </select>
                    <mat-icon class="chevron">expand_more</mat-icon>
                  </div>
                </div>
              </div>

              <!-- Pre-call checkbox -->
              <label class="precall-card">
                <input type="checkbox" name="preCal" [(ngModel)]="form.pre_call" class="precall-check">
                <div class="precall-text">
                  <span class="precall-title">Extract requirements before estimating (pre_call)</span>
                  <span class="precall-desc">Use AI to extract and structure requirements before generating the estimate.</span>
                </div>
                <mat-icon class="precall-info">info_outline</mat-icon>
              </label>

              <!-- Advanced options (collapsed) -->
              <mat-expansion-panel class="advanced-panel">
                <mat-expansion-panel-header>
                  <mat-panel-title>Advanced options</mat-panel-title>
                  <mat-panel-description>Project type, sampling &amp; generation parameters</mat-panel-description>
                </mat-expansion-panel-header>

                <div class="selects-row adv-row">
                  <div class="select-group">
                    <label class="select-label">
                      <mat-icon class="select-icon">smart_toy</mat-icon> Model
                    </label>
                    <div class="select-wrap">
                      <select class="select" name="model" [(ngModel)]="form.model">
                        <option value="">Select model</option>
                        <option value="gpt-4o-mini">GPT-4o mini</option>
                        <option value="gpt-5.4-mini">GPT-5.4 mini</option>
                        <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                        <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
                      </select>
                      <mat-icon class="chevron">expand_more</mat-icon>
                    </div>
                  </div>
                  <div class="select-group">
                    <label class="select-label"><mat-icon class="select-icon">format_list_bulleted</mat-icon> Example format</label>
                    <div class="select-wrap">
                      <select class="select" name="exampleFormat" [(ngModel)]="form.example_format">
                        <option value="markdown">Markdown</option>
                        <option value="json">JSON</option>
                        <option value="narrative">Narrative</option>
                      </select>
                      <mat-icon class="chevron">expand_more</mat-icon>
                    </div>
                  </div>
                  <div class="select-group">
                    <label class="select-label">
                      <mat-icon class="select-icon">auto_awesome</mat-icon> Prompt version
                    </label>
                    <div class="select-wrap">
                      <select class="select" name="promptVersion" [(ngModel)]="form.prompt_version">
                        <option value="v1">v1</option>
                        <option value="v2">v2</option>
                      </select>
                      <mat-icon class="chevron">expand_more</mat-icon>
                    </div>
                  </div>
                </div>

                <div class="selects-row adv-row">
                  <div class="select-group">
                    <label class="select-label"><mat-icon class="select-icon">psychology</mat-icon> Reasoning effort</label>
                    <div class="select-wrap">
                      <select class="select" name="reasoningEffort" [(ngModel)]="form.reasoning_effort">
                        <option value="low">Low</option>
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                      </select>
                      <mat-icon class="chevron">expand_more</mat-icon>
                    </div>
                  </div>
                  <div class="input-group">
                    <label class="select-label"><mat-icon class="select-icon">thermostat</mat-icon> Temperature (0–1)</label>
                    <input class="text-input" type="number" name="temperature"
                      [(ngModel)]="form.temperature" min="0" max="1" step="0.05" placeholder="Default">
                  </div>
                  <div class="input-group">
                    <label class="select-label"><mat-icon class="select-icon">format_list_numbered</mat-icon> Examples (0–5)</label>
                    <input class="text-input" type="number" name="numExamples"
                      [(ngModel)]="form.num_examples" min="0" max="5" step="1">
                  </div>
                  <div class="input-group">
                    <label class="select-label"><mat-icon class="select-icon">token</mat-icon> Max output tokens</label>
                    <input class="text-input" type="number" name="maxOutputTokens"
                      [(ngModel)]="form.max_output_tokens" min="256" max="32768" step="256">
                  </div>
                </div>
              </mat-expansion-panel>

              <!-- Reference projects -->
              <div class="ref-section">
                <div class="ref-section-head">
                  <span class="field-label">Reference projects <em class="optional-tag">(optional)</em></span>
                </div>
                <div class="ref-counter-row">
                  <span class="select-label">Number of reference projects</span>
                  <div class="counter-ctrl">
                    <span class="counter-val">{{ refProjects.length }}</span>
                    <button type="button" class="counter-btn" (click)="removeRefProject()" [disabled]="refProjects.length === 0">−</button>
                    <button type="button" class="counter-btn counter-btn--add" (click)="addRefProject()">+</button>
                  </div>
                </div>
                @for (proj of refProjects; track $index; let i = $index) {
                  <div class="ref-project">
                    <div class="ref-project-title">Project {{ i + 1 }}</div>
                    <div class="ref-row">
                      <div class="ref-col ref-col--name">
                        <label class="select-label">Name</label>
                        <input class="text-input" type="text" [name]="'refName' + i"
                          [(ngModel)]="proj.name" placeholder="e.g. HR Tool v1">
                      </div>
                      <div class="ref-col ref-col--desc">
                        <label class="select-label">Description</label>
                        <input class="text-input" type="text" [name]="'refDesc' + i"
                          [(ngModel)]="proj.description" placeholder="e.g. Basic HR CRUD app">
                      </div>
                      <div class="ref-col ref-col--num">
                        <label class="select-label">Hours</label>
                        <div class="num-ctrl">
                          <input class="text-input num-input" type="number" [name]="'refHours' + i"
                            [(ngModel)]="proj.total_hours" min="0" placeholder="0">
                          <button type="button" class="counter-btn" (click)="proj.total_hours = (proj.total_hours ?? 0) - 1" [disabled]="(proj.total_hours ?? 0) <= 0">−</button>
                          <button type="button" class="counter-btn counter-btn--add" (click)="proj.total_hours = (proj.total_hours ?? 0) + 1">+</button>
                        </div>
                      </div>
                      <div class="ref-col ref-col--num">
                        <label class="select-label">Cost (EUR)</label>
                        <div class="num-ctrl">
                          <input class="text-input num-input" type="number" [name]="'refCost' + i"
                            [(ngModel)]="proj.total_cost" min="0" placeholder="0">
                          <button type="button" class="counter-btn" (click)="proj.total_cost = (proj.total_cost ?? 0) - 1" [disabled]="(proj.total_cost ?? 0) <= 0">−</button>
                          <button type="button" class="counter-btn counter-btn--add" (click)="proj.total_cost = (proj.total_cost ?? 0) + 1">+</button>
                        </div>
                      </div>
                    </div>
                  </div>
                }
              </div>

              @if (guardrailError()) {
                <div class="guardrail-warning" [attr.data-reason]="guardrailError()!.reason">
                  <mat-icon>{{ guardrailIcon(guardrailError()!.reason) }}</mat-icon>
                  <span>{{ guardrailError()!.message }}</span>
                </div>
              }
              @if (error()) {
                <p class="error-msg">{{ error() }}</p>
              }

              <!-- Submit button -->
              <div class="form-actions">
                <button type="submit" class="btn-primary" [disabled]="loading() || !form.transcription.trim()">
                  @if (loading()) {
                    <mat-spinner diameter="16"></mat-spinner>
                    <span>{{ isStreaming() ? 'Generating...' : 'Processing...' }}</span>
                  } @else {
                    <mat-icon>send</mat-icon>
                    <span>Estimate</span>
                  }
                </button>
              </div>
            </form>
                </div>
              }

              <!-- Response Tab -->
              @if (activeTab() === 'response') {
                <div class="tab-pane tab-response">
                  @if (!isStreaming() && !streamingResult() && !error() && !guardrailError()) {
                    <div class="empty-state">
                      <mat-icon>inbox</mat-icon>
                      <p>No hay respuestas aún. Completa el formulario y presiona "Estimate" para generar una.</p>
                    </div>
                  } @else {
                    <app-estimation-result
                      [inlineMarkdown]="responseMarkdown()"
                      [inlineResponse]="responsePayload()"
                      [inlineLoading]="isStreaming()"
                      [inlineError]="error() ?? guardrailError()?.message ?? null">
                    </app-estimation-result>
                  }
                </div>
              }
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .page {
      height: calc(100vh - 64px);
      background: #fff;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .chat-container {
      display: flex;
      flex-direction: column;
      height: 100%;
      background: #fff;
    }

    /* Header */
    .chat-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      border-bottom: 1px solid #e8e8f0;
      background: #f8f8fc;
      flex-shrink: 0;
      gap: 12px;
    }
    .header-left {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }
    .head-title {
      margin: 0;
      font-size: 1.2rem;
      font-weight: 600;
      color: #1a1a2e;
    }
    .head-sub {
      margin: 0;
      font-size: 0.75rem;
      color: #999;
    }
    .btn-secondary {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: 8px;
      border: 1px solid #d5d9f5;
      background: #fff;
      color: #3f51b5;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.8rem;
    }
    .btn-secondary:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .btn-secondary:hover:not(:disabled) {
      background: #f5f0ff;
    }
    .btn-secondary mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }

    /* Sidebar toggle button */
    .btn-sidebar-toggle {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border-radius: 8px;
      border: 1px solid #e8e8f0;
      background: #fff;
      color: #666;
      cursor: pointer;
      transition: all 0.2s;
      font-size: 0;
    }
    .btn-sidebar-toggle:hover {
      background: #f5f0ff;
      border-color: #d5d9f5;
      color: #5c6bc0;
    }
    .btn-sidebar-toggle.active {
      background: #5c6bc0;
      border-color: #5c6bc0;
      color: #fff;
    }
    .btn-sidebar-toggle mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }

    /* Layout wrapper */
    .layout-wrapper {
      display: flex;
      flex: 1;
      overflow: hidden;
      gap: 0;
    }

    /* Sidebar */
    .sidebar {
      width: 320px;
      border-right: 1px solid #e8e8f0;
      background: #fafbff;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: slideInRight 0.3s ease-out;
    }
    @keyframes slideInRight {
      from {
        width: 0;
        opacity: 0;
      }
      to {
        width: 320px;
        opacity: 1;
      }
    }
    .sidebar-header {
      padding: 16px;
      border-bottom: 1px solid #e8e8f0;
      flex-shrink: 0;
    }
    .sidebar-header h3 {
      margin: 0 0 4px 0;
      font-size: 0.9rem;
      font-weight: 700;
      color: #1a1a2e;
    }
    .sidebar-hint {
      font-size: 0.7rem;
      color: #999;
      font-style: italic;
    }
    .sidebar-content {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .sidebar-content::-webkit-scrollbar {
      width: 6px;
    }
    .sidebar-content::-webkit-scrollbar-track {
      background: transparent;
    }
    .sidebar-content::-webkit-scrollbar-thumb {
      background: #d0d0e8;
      border-radius: 3px;
    }
    .sidebar-content::-webkit-scrollbar-thumb:hover {
      background: #b0b0c8;
    }

    /* Metadata sections in sidebar */
    .metadata-section {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px;
      background: #fff;
      border: 1px solid #e8e8f0;
      border-radius: 6px;
    }
    .metadata-label {
      font-size: 0.7rem;
      font-weight: 700;
      color: #5c6bc0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .metadata-value {
      font-size: 0.8rem;
      color: #333;
      word-break: break-word;
      font-family: 'Monaco', 'Courier New', monospace;
    }
    .metadata-value.session-id {
      font-size: 0.75rem;
      color: #666;
    }
    .req-list {
      margin: 0;
      padding-left: 16px;
      font-size: 0.75rem;
      color: #333;
    }
    .req-list li {
      margin-bottom: 4px;
    }
    .metadata-json-full {
      margin: 0;
      padding: 8px;
      background: #f0f0f8;
      border: 1px solid #e5e5f0;
      border-radius: 4px;
      font-size: 0.65rem;
      line-height: 1.3;
      max-height: 200px;
      overflow-y: auto;
      color: #333;
    }
    .metadata-empty {
      padding: 16px;
      text-align: center;
      color: #999;
      font-size: 0.8rem;
    }

    /* Main chat area */
    .chat-area { display: flex; flex-direction: column; flex: 1; overflow: hidden; padding: 0; }

    /* Tabs */
    .tabs-header { display: flex; gap: 0; border-bottom: 2px solid #e8e8f0; background: #f8f8fc; padding: 0 24px; }
    .tab-button { display: flex; align-items: center; gap: 8px; padding: 16px 0; border: none; background: none; cursor: pointer; font-size: 0.9rem; font-weight: 500; color: #666; border-bottom: 3px solid transparent; margin: 0 16px; transition: all 0.2s; }
    .tab-button:hover { color: #5c6bc0; }
    .tab-button.tab-active { color: #5c6bc0; border-bottom-color: #5c6bc0; }
    .tab-button mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .tab-badge { width: 8px; height: 8px; border-radius: 50%; background: #ff5252; margin-left: 4px; animation: pulse 0.5s infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

    .tabs-content { display: flex; flex: 1; overflow: hidden; }
    .tab-pane { display: flex; flex-direction: column; width: 100%; overflow-y: auto; padding: 24px; gap: 24px; }
    .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; height: 100%; color: #999; text-align: center; }
    .empty-state mat-icon { font-size: 64px; width: 64px; height: 64px; color: #ddd; }
    .empty-state p { font-size: 0.9rem; margin: 0; max-width: 300px; }

    /* Input section - now part of tab-pane */
    .chat-form {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .field {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: #555;
    }
    .required {
      color: #5c6bc0;
    }
    .optional-tag {
      font-size: 0.7rem;
      color: #999;
      font-style: italic;
    }

    .textarea {
      width: 100%;
      padding: 10px 12px;
      border: 1.5px solid #e8e8f0;
      border-radius: 8px;
      font-size: 0.85rem;
      font-family: inherit;
      resize: vertical;
      min-height: 80px;
      max-height: 120px;
      color: #333;
      transition: border-color 0.2s;
    }
    .textarea:focus {
      outline: none;
      border-color: #5c6bc0;
      box-shadow: 0 0 0 3px rgba(92,107,192,0.12);
    }
    .textarea::placeholder {
      color: #bbb;
    }
    .textarea-footer {
      display: flex;
      justify-content: flex-end;
      font-size: 0.7rem;
      color: #999;
    }
    .char-count {
      color: #aaa;
    }

    /* Attachments */
    .attach-zone {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 12px;
      border: 2px dashed #d0d0e8;
      border-radius: 8px;
      background: #fafafa;
      cursor: pointer;
      text-align: center;
      transition: border-color 0.2s, background 0.2s;
    }
    .attach-zone:hover,
    .attach-zone:focus,
    .attach-zone--drag {
      border-color: #5c6bc0;
      background: #f5f0ff;
    }
    .attach-icon {
      font-size: 20px;
      width: 20px;
      height: 20px;
      color: #8c87c2;
    }
    .attach-label {
      font-size: 0.75rem;
      color: #555;
    }

    .file-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 6px;
    }
    .file-chip {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 6px;
      background: #f5f0ff;
      border: 1px solid #d8d2f8;
      font-size: 0.75rem;
    }
    .file-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
      color: #5c6bc0;
      flex-shrink: 0;
    }
    .file-name {
      flex: 1;
      color: #333;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 500;
    }
    .file-remove {
      background: none;
      border: none;
      cursor: pointer;
      padding: 0;
      color: #aaa;
      display: flex;
      align-items: center;
      border-radius: 2px;
      transition: color 0.2s;
      flex-shrink: 0;
    }
    .file-remove:hover {
      color: #e53935;
    }
    .file-remove mat-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }

    /* Options rows */
    .selects-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .adv-row {
      margin-top: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .select-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .select-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: #555;
    }
    .select {
      padding: 8px 10px;
      border: 1.5px solid #e8e8f0;
      border-radius: 6px;
      font-size: 0.8rem;
      color: #333;
      cursor: pointer;
      transition: border-color 0.2s;
      appearance: none;
      -webkit-appearance: none;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 6px center;
      background-size: 16px;
      padding-right: 28px;
    }
    .select-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }
    .select-wrap .select {
      width: 100%;
      background-image: none;
      padding-right: 30px;
    }
    .select-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
      margin-right: 4px;
      color: #7c84c8;
      vertical-align: text-bottom;
    }
    .chevron {
      position: absolute;
      right: 8px;
      font-size: 18px;
      width: 18px;
      height: 18px;
      color: #999;
      pointer-events: none;
    }
    .select:focus {
      outline: none;
      border-color: #5c6bc0;
      box-shadow: 0 0 0 3px rgba(92,107,192,0.12);
    }

    .input-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .text-input {
      width: 100%;
      padding: 8px 10px;
      border: 1.5px solid #e8e8f0;
      border-radius: 6px;
      font-size: 0.8rem;
      color: #333;
      transition: border-color 0.2s, box-shadow 0.2s;
      min-width: 0;
    }
    .text-input:focus {
      outline: none;
      border-color: #5c6bc0;
      box-shadow: 0 0 0 3px rgba(92,107,192,0.12);
    }
    .num-input {
      text-align: right;
    }

    .precall-card {
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: 10px;
      border: 1px solid #e8e8f0;
      background: #fafbff;
      border-radius: 8px;
      padding: 10px 12px;
    }
    .precall-check {
      margin: 0;
      accent-color: #5c6bc0;
    }
    .precall-text {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .precall-title {
      font-size: 0.78rem;
      font-weight: 600;
      color: #2f3460;
    }
    .precall-desc {
      font-size: 0.72rem;
      color: #666;
      line-height: 1.35;
    }
    .precall-info {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: #7c84c8;
    }

    .advanced-panel {
      margin-top: 4px;
      border-radius: 8px !important;
      border: 1px solid #e8e8f0 !important;
      box-shadow: none !important;
    }

    .ref-section {
      border: 1px solid #ececf6;
      border-radius: 10px;
      background: #fcfcff;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .ref-counter-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .counter-ctrl {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .counter-val {
      min-width: 24px;
      text-align: center;
      font-weight: 600;
      color: #2f3460;
    }
    .counter-btn {
      border: 1px solid #d9dff2;
      background: #fff;
      color: #4f5fb5;
      width: 26px;
      height: 26px;
      border-radius: 6px;
      cursor: pointer;
      line-height: 1;
    }
    .counter-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .counter-btn--add {
      background: #eef0ff;
      border-color: #cfd5fa;
      font-weight: 700;
    }
    .ref-project {
      border: 1px solid #e7eaf7;
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .ref-project-title {
      font-size: 0.75rem;
      font-weight: 700;
      color: #3f51b5;
      margin-bottom: 8px;
    }
    .ref-row {
      display: grid;
      grid-template-columns: 2fr 3fr 1fr 1fr;
      gap: 8px;
    }
    .ref-col {
      min-width: 0;
    }
    .num-ctrl {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 6px;
      align-items: center;
    }

    .guardrail-warning,
    .error-msg {
      margin: 0;
      font-size: 0.78rem;
    }
    .guardrail-warning {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border: 1px solid #ffdca8;
      background: #fff8ec;
      border-radius: 8px;
      color: #a05900;
    }
    .error-msg {
      color: #c62828;
      font-weight: 500;
    }

    @media (max-width: 1100px) {
      .selects-row,
      .adv-row,
      .ref-row {
        grid-template-columns: 1fr 1fr;
      }
      .sidebar {
        width: 280px;
      }
    }
    @media (max-width: 900px) {
      .sidebar {
        width: 240px;
      }
    }
    @media (max-width: 760px) {
      .chat-area {
        padding: 14px;
        gap: 14px;
      }
      .selects-row,
      .adv-row,
      .ref-row {
        grid-template-columns: 1fr;
      }
      .precall-card {
        grid-template-columns: auto 1fr;
      }
      .precall-info {
        display: none;
      }
      .sidebar {
        position: absolute;
        top: 60px;
        right: 0;
        width: 100%;
        max-width: 280px;
        height: calc(100vh - 60px);
        z-index: 100;
        box-shadow: -2px 0 8px rgba(0,0,0,0.1);
      }
    }

    /* Form actions */
    .form-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .btn-primary {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 10px 20px;
      border-radius: 8px;
      background: #5c6bc0;
      color: #fff;
      font-size: 0.85rem;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: background 0.2s, box-shadow 0.2s;
      box-shadow: 0 2px 8px rgba(92,107,192,0.3);
    }
    .btn-primary:hover:not(:disabled) {
      background: #3f51b5;
      box-shadow: 0 4px 12px rgba(92,107,192,0.4);
    }
    .btn-primary:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      box-shadow: none;
    }
    .btn-primary mat-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
  `],
})
export class EstimationFormComponent implements OnInit {
  form: EstimationCreate = {
    transcription: '',
    output_format: 'phases_table',
    example_format: 'markdown',
    prompt_version: 'v1',
    pre_call: false,
    num_examples: 3,
    max_output_tokens: 2048,
    reasoning_effort: 'medium',
  };

  loading = signal(false);
  error = signal<string | null>(null);
  guardrailError = signal<GuardrailError | null>(null);
  attachments = signal<File[]>([]);
  inlineResult = signal<SessionEstimationResponse | null>(null);
  streamingResult = signal<string>('');
  responsePayload = computed(() => this.extractSessionResponse(this.streamingResult()));
  responseMarkdown = computed(() => this.responsePayload()?.estimation ?? this.streamingResult());
  isStreaming = signal(false);
  dragOver = signal(false);
  sessionId = signal<string | null>(null);
  projectMetadata = signal<SessionProjectMetadata | null>(null);
  historyMessageCount = signal(0);
  turnCount = signal(0);
  cacheMetrics = signal<CacheMetrics | null>(null);
  cacheMetricsLoading = signal(false);
  cacheMetricsError = signal<string | null>(null);
  isExistingSession = signal(false);
  sidebarOpen = signal(false);
  activeTab = signal<'form' | 'response'>('form');

  refProjects: ReferenceProject[] = [];

  addRefProject() {
    this.refProjects.push({ name: '', description: '', total_hours: null, total_cost: null });
  }

  removeRefProject() {
    this.refProjects.pop();
  }

  onFilesSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.attachments.update(prev => [...prev, ...Array.from(input.files!)]);
      input.value = '';
    }
  }

  removeAttachment(index: number) {
    this.attachments.update(prev => prev.filter((_, i) => i !== index));
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(true);
  }

  onDragLeave(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(false);
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragOver.set(false);
    const files = event.dataTransfer?.files;
    if (files) {
      this.attachments.update(prev => [...prev, ...Array.from(files)]);
    }
  }

  fileIcon(file: File): string {
    const name = file.name.toLowerCase();
    if (name.endsWith('.pdf') || file.type === 'application/pdf') return 'picture_as_pdf';
    if (name.endsWith('.docx')) return 'description';
    if (name.endsWith('.txt') || file.type === 'text/plain') return 'text_snippet';
    return 'attach_file';
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  formatCost(cost: number): string {
    return '$' + cost.toFixed(6);
  }

  toggleSidebar() {
    this.sidebarOpen.update(value => {
      const next = !value;
      if (next) {
        this.refreshCacheMetrics();
      }
      return next;
    });
  }

  refreshCacheMetrics() {
    this.cacheMetricsLoading.set(true);
    this.cacheMetricsError.set(null);
    this.estimationService.getCacheMetrics().subscribe({
      next: (metrics: CacheMetrics) => {
        this.cacheMetrics.set(metrics);
        this.cacheMetricsLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const msg = err?.error?.detail ?? err?.message ?? 'Unable to load cache metrics';
        this.cacheMetricsError.set(String(msg));
        this.cacheMetricsLoading.set(false);
      },
    });
  }

  constructor(
    private readonly estimationService: EstimationService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {
    this.route.queryParams.subscribe(p => {
      if (p['projectId']) this.form.project_id = p['projectId'];
    });
  }

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      if (params['sessionId']) {
        // Load existing session
        this.isExistingSession.set(true);
        this.sessionId.set(params['sessionId']);
        this._refreshSessionState(params['sessionId']);
      } else {
        // Create new session
        this.isExistingSession.set(false);
        this.startNewConversation();
      }
    });
  }

  guardrailIcon(reason: GuardrailReason): string {
    return GUARDRAIL_ICONS[reason] ?? 'warning';
  }

  submit() {
    if (!this.sessionId()) {
      this.error.set('No active session. Please create a new conversation.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    this.guardrailError.set(null);
    this.inlineResult.set(null);

    this._submitWithSession();
  }

  startNewConversation() {
    this.loading.set(true);
    this.error.set(null);
    this.guardrailError.set(null);
    this.inlineResult.set(null);
    this.attachments.set([]);

    this.estimationService.createSession().subscribe({
      next: ({ session_id }) => {
        this.sessionId.set(session_id);
        this._refreshSessionState(session_id);
      },
      error: (err: HttpErrorResponse) => this._handleError(err),
    });
  }

  private _submitWithSession() {
    const sessionId = this.sessionId();
    if (!sessionId) {
      this.loading.set(false);
      this.error.set('No active session. Please create a new conversation.');
      return;
    }

    const fd = new FormData();
    fd.append('transcript', this.form.transcription);
    this.attachments().forEach(f => fd.append('attachments', f, f.name));
    if (this.form.model) fd.append('model', this.form.model);
    if (this.form.temperature != null) fd.append('temperature', String(this.form.temperature));
    fd.append('pre_call', String(this.form.pre_call ?? false));
    fd.append('output_format', this.form.output_format ?? 'phases_table');

    // Use streaming
    this.streamingResult.set('');
    this.isStreaming.set(true);
    this.loading.set(true);

    this.estimationService.createWithAttachmentsStream(
      sessionId,
      fd,
      this.form.prompt_version,
    ).subscribe({
      next: (chunk: string) => {
        this.streamingResult.update(prev => prev + chunk);
      },
      error: (err: unknown) => {
        this.isStreaming.set(false);
        this._handleError(err);
      },
      complete: () => {
        this.isStreaming.set(false);
        this.loading.set(false);
        if (this.sidebarOpen()) {
          this.refreshCacheMetrics();
        }
        // Refresh session state after streaming completes
        this.estimationService.getSessionState(sessionId).subscribe({
          next: sessionState => {
            this.projectMetadata.set(sessionState.project_metadata);
            this.historyMessageCount.set(sessionState.history.length);
            this.turnCount.set(sessionState.turn_count);
          },
          error: (err: HttpErrorResponse) => this._handleError(err),
        });
      },
    });
  }

  private _refreshSessionState(sessionId: string) {
    this.estimationService.getSessionState(sessionId).subscribe({
      next: sessionState => {
        this.projectMetadata.set(sessionState.project_metadata);
        this.historyMessageCount.set(sessionState.history.length);
        this.turnCount.set(sessionState.turn_count);
        if (this.sidebarOpen()) {
          this.refreshCacheMetrics();
        }
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => this._handleError(err),
    });
  }

  private _submitJson() {
    const validRefs = this.refProjects.filter(r => r.name.trim() && r.description.trim());
    this.form.reference_projects = validRefs.length > 0 ? validRefs : undefined;
    this.estimationService.create(this.form).subscribe({
      next: result => {
        this.router.navigate(['/estimations', result.id]);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => this._handleError(err),
    });
  }

  private extractSessionResponse(raw: string): SessionEstimationResponse | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;

    if (trimmed.startsWith('{') && trimmed.includes('"estimation"')) {
      try {
        const parsed = JSON.parse(trimmed) as Partial<SessionEstimationResponse>;
        if (typeof parsed.estimation === 'string') {
          return parsed as SessionEstimationResponse;
        }
      } catch {
        // During streaming, payload can be partial JSON; fallback to raw text.
      }
    }

    return null;
  }

  private _handleError(err: unknown) {
    let detail: any = null;
    let status: number | null = null;
    let message: string = 'Unknown error';

    // Handle structured error object from streaming service
    if (err && typeof err === 'object' && 'status' in err && 'detail' in err) {
      status = (err as any).status;
      detail = (err as any).detail;
    }
    // Handle HttpErrorResponse
    else if (err instanceof HttpErrorResponse) {
      status = err.status;
      detail = err.error?.detail;
      message = err.message;
    }
    // Handle generic Error
    else if (err instanceof Error) {
      message = err.message;
    }

    // Check if it's a guardrail error
    if (detail?.reason && (status === 400 || status === 422)) {
      this.guardrailError.set(detail as GuardrailError);
    } else {
      const msg = typeof detail === 'string' ? detail : (detail?.message ?? message ?? 'Unknown error');
      this.error.set(`Estimation failed${status ? ` (${status})` : ''}: ${msg}`);
    }
    this.loading.set(false);
  }
}
