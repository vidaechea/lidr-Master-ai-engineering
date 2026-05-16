import { Component, OnInit, signal } from '@angular/core';
import { JsonPipe, TitleCasePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { switchMap } from 'rxjs';
import {
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
  imports: [FormsModule, JsonPipe, TitleCasePipe, MatExpansionModule, MatIconModule, MatProgressSpinnerModule],
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
        </div>

        <!-- Main chat area (messages + input scrollable) -->
        <div class="chat-area">
          <!-- Messages/Results section -->
          <div class="messages-section">
            <!-- Streaming result -->
            @if (isStreaming() || streamingResult()) {
              <div class="message message-ai">
                <div class="message-header">
                  <mat-icon class="ai-icon">auto_awesome</mat-icon>
                  <span class="ai-label">Estimation</span>
                  @if (isStreaming()) {
                    <span class="streaming-indicator">
                      <span class="dot"></span>
                      <span class="dot"></span>
                      <span class="dot"></span>
                    </span>
                  }
                </div>
                <div class="message-content">
                  <pre class="result-text">{{ streamingResult() }}</pre>
                  @if (isStreaming()) {
                    <span class="cursor">|</span>
                  }
                </div>
              </div>
            }

            <!-- Error state -->
            @if (error()) {
              <div class="message message-error">
                <div class="message-header">
                  <mat-icon>error</mat-icon>
                  <span>Error</span>
                </div>
                <div class="message-content">{{ error() }}</div>
              </div>
            }

            <!-- Guardrail error state -->
            @if (guardrailError()) {
              <div class="message message-warning">
                <div class="message-header">
                  <mat-icon>{{ guardrailIcon(guardrailError()!.reason) }}</mat-icon>
                  <span>{{ guardrailError()!.reason | titlecase }}</span>
                </div>
                <div class="message-content">{{ guardrailError()!.message }}</div>
              </div>
            }

            <!-- Metadata panel -->
            @if (turnCount() > 0 || historyMessageCount() > 0) {
              <mat-expansion-panel class="metadata-panel">
                <mat-expansion-panel-header>
                  <mat-panel-title>Session Metadata</mat-panel-title>
                  <mat-panel-description>
                    {{ turnCount() }} turns · {{ historyMessageCount() }} messages
                  </mat-panel-description>
                </mat-expansion-panel-header>
                @if (projectMetadata(); as metadata) {
                  <pre class="metadata-json">{{ metadata | json }}</pre>
                } @else {
                  <p class="metadata-empty">No metadata yet for this session.</p>
                }
              </mat-expansion-panel>
            }
          </div>

          <!-- Input form section -->
          <div class="input-section">
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
              <div class="options-row">
                <div class="select-group">
                  <label class="select-label">Output format</label>
                  <select class="select" name="outputFormat" [(ngModel)]="form.output_format">
                    <option value="phases_table">Phases table</option>
                    <option value="line_items">Line items</option>
                    <option value="narrative">Narrative</option>
                  </select>
                </div>
                <div class="select-group">
                  <label class="select-label">Model</label>
                  <select class="select" name="model" [(ngModel)]="form.model">
                    <option value="">Auto</option>
                    <option value="gpt-4o-mini">GPT-4o mini</option>
                    <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                    <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</option>
                  </select>
                </div>
              </div>

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
    }
    .header-left {
      display: flex;
      flex-direction: column;
      gap: 4px;
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

    /* Main chat area */
    .chat-area {
      display: flex;
      flex-direction: column;
      flex: 1;
      overflow: hidden;
      padding: 24px;
      gap: 24px;
    }

    /* Messages section (scrollable) */
    .messages-section {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding-right: 8px;
    }
    .messages-section::-webkit-scrollbar {
      width: 8px;
    }
    .messages-section::-webkit-scrollbar-track {
      background: transparent;
    }
    .messages-section::-webkit-scrollbar-thumb {
      background: #d0d0e8;
      border-radius: 4px;
    }
    .messages-section::-webkit-scrollbar-thumb:hover {
      background: #b0b0c8;
    }

    /* Messages */
    .message {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 16px;
      border-radius: 12px;
      max-width: 90%;
      animation: slideIn 0.3s ease-out;
    }
    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .message-ai {
      background: #f5f0ff;
      border: 1.5px solid #d8d2f8;
      align-self: flex-start;
    }
    .message-error {
      background: #fce4ec;
      border: 1.5px solid #f48fb1;
      color: #c62828;
      align-self: flex-start;
    }
    .message-warning {
      background: #fff8e1;
      border: 1.5px solid #ffe082;
      color: #e65100;
      align-self: flex-start;
    }

    .message-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      color: #5c6bc0;
    }
    .ai-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
    }
    .ai-label {
      color: #5c6bc0;
    }

    .streaming-indicator {
      display: flex;
      gap: 3px;
      margin-left: auto;
    }
    .dot {
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: #5c6bc0;
      animation: blink 1s infinite;
    }
    .dot:nth-child(2) {
      animation-delay: 0.2s;
    }
    .dot:nth-child(3) {
      animation-delay: 0.4s;
    }
    @keyframes blink {
      0%, 100% { opacity: 0.3; }
      50% { opacity: 1; }
    }

    .message-content {
      font-size: 0.875rem;
      color: #333;
      line-height: 1.6;
    }
    .result-text {
      margin: 0;
      white-space: pre-wrap;
      font-family: 'Monaco', 'Courier New', monospace;
      font-size: 0.8rem;
      max-height: 300px;
      overflow-y: auto;
      color: #333;
    }
    .cursor {
      animation: blink-cursor 1s infinite;
      margin-left: 2px;
    }
    @keyframes blink-cursor {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }

    /* Metadata panel */
    .metadata-panel {
      margin-top: 16px;
      border-radius: 8px !important;
      border: 1.5px solid #e8e8f0 !important;
      box-shadow: none !important;
    }
    .metadata-json {
      margin: 0;
      padding: 12px;
      border-radius: 8px;
      background: #f7f9fc;
      border: 1px solid #e5e9f1;
      font-size: 0.75rem;
      line-height: 1.4;
      max-height: 150px;
      overflow-y: auto;
    }
    .metadata-empty {
      margin: 0;
      color: #777;
      font-size: 0.8rem;
    }

    /* Input section (fixed at bottom) */
    .input-section {
      flex-shrink: 0;
      border-top: 1px solid #e8e8f0;
      padding-top: 16px;
      max-height: 50vh;
      overflow-y: auto;
    }
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

    /* Options row */
    .options-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
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
    .select:focus {
      outline: none;
      border-color: #5c6bc0;
      box-shadow: 0 0 0 3px rgba(92,107,192,0.12);
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
  isStreaming = signal(false);
  dragOver = signal(false);
  sessionId = signal<string | null>(null);
  projectMetadata = signal<SessionProjectMetadata | null>(null);
  historyMessageCount = signal(0);
  turnCount = signal(0);
  isExistingSession = signal(false);

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
      error: (err: HttpErrorResponse) => {
        this.isStreaming.set(false);
        this._handleError(err);
      },
      complete: () => {
        this.isStreaming.set(false);
        this.loading.set(false);
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

  private _handleError(err: HttpErrorResponse) {
    const detail = err.error?.detail;
    if (detail?.reason && (err.status === 400 || err.status === 422)) {
      this.guardrailError.set(detail as GuardrailError);
    } else {
      const msg = typeof detail === 'string' ? detail : (detail?.message ?? err.message ?? 'Unknown error');
      this.error.set(`Estimation failed (${err.status}): ${msg}`);
    }
    this.loading.set(false);
  }
}
