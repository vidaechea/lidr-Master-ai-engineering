import { Component, signal } from '@angular/core';
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
  imports: [FormsModule, MatExpansionModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="page">
      <div class="card">

        <!-- Card header -->
        <div class="card-head">
          <div class="head-icon"><mat-icon>description</mat-icon></div>
          <div>
            <h2 class="head-title">New Estimation</h2>
            <p class="head-sub">Paste a meeting transcript or project description to generate an estimate</p>
          </div>
        </div>
        <hr class="divider">

        <form (ngSubmit)="submit()">

          <!-- Transcript -->
          <div class="field">
            <div class="field-header">
              <label class="field-label" for="transcription">
                Transcript / Description <span class="required">*</span>
              </label>
              <span class="tip-badge">
                <mat-icon class="tip-icon">lightbulb</mat-icon>
                Tip: Include goals, scope, and key requirements
              </span>
            </div>
            <textarea id="transcription" class="textarea" name="transcription"
              [(ngModel)]="form.transcription"
              rows="8" maxlength="20000" required minlength="20"
              placeholder="Paste meeting transcript or project description here...">
            </textarea>
            <div class="textarea-footer">
              <span class="char-count">{{ form.transcription.length }} / 20,000</span>
            </div>
          </div>

          <!-- Attachments drop-zone -->
          <div class="field">
            <div class="field-header">
              <label class="field-label">
                Attachments <em class="optional-tag">(optional)</em>
              </label>
              <span class="tip-badge">
                <mat-icon class="tip-icon">info</mat-icon>
                PDF, DOCX or TXT — text extracted server-side
              </span>
            </div>
            <div class="attach-zone" [class.attach-zone--drag]="dragOver()"
              (dragover)="onDragOver($event)" (dragleave)="onDragLeave($event)" (drop)="onDrop($event)"
              (click)="fileInput.click()" (keydown.enter)="fileInput.click()" tabindex="0" role="button"
              aria-label="Upload attachments">
              <input #fileInput type="file" accept=".pdf,.docx,.txt" multiple hidden
                (change)="onFilesSelected($event)">
              <mat-icon class="attach-icon">cloud_upload</mat-icon>
              <span class="attach-label">Drop files here or <strong>click to browse</strong></span>
              <span class="attach-hint">PDF · DOCX · TXT — max 10 MB each</span>
            </div>
            @if (attachments().length > 0) {
              <div class="file-list">
                @for (f of attachments(); track $index; let i = $index) {
                  <div class="file-chip">
                    <mat-icon class="file-icon">{{ fileIcon(f) }}</mat-icon>
                    <span class="file-name">{{ f.name }}</span>
                    <span class="file-size">({{ formatSize(f.size) }})</span>
                    <button type="button" class="file-remove" (click)="removeAttachment(i)"
                      [attr.aria-label]="'Remove ' + f.name">
                      <mat-icon>close</mat-icon>
                    </button>
                  </div>
                }
              </div>
            }
          </div>

          <!-- Primary row: Model / Output format / Prompt version -->
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

          <div class="form-actions">
            <button type="submit" class="btn-primary" [disabled]="loading()">
              @if (loading()) {
                <mat-spinner diameter="18"></mat-spinner>
                <span>Running…</span>
              } @else {
                <mat-icon>auto_awesome</mat-icon>
                <span>Run Estimation</span>
              }
            </button>
          </div>
        </form>

        <!-- Inline result (shown when attachments path is used) -->
        @if (inlineResult()) {
          <div class="inline-result">
            <div class="inline-result-head">
              <mat-icon>auto_awesome</mat-icon>
              <span>Estimation Result</span>
              <span class="inline-model">{{ inlineResult()!.model }}</span>
            </div>
            <div class="inline-result-body">{{ inlineResult()!.estimation }}</div>
            <div class="inline-result-meta">
              <span>Tokens: {{ inlineResult()!.input_tokens }} in / {{ inlineResult()!.output_tokens }} out</span>
              <span>Cost: {{ formatCost(inlineResult()!.turn_cost_usd) }}</span>
            </div>
          </div>
        }

      </div>
    </div>
  `,
  styles: [`
    .page {
      min-height: calc(100vh - 64px);
      background: #f0f0f5;
      padding: 32px 16px;
      margin: -24px -16px;
    }
    .card {
      max-width: 840px; margin: 0 auto;
      background: #fff; border-radius: 16px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.08); padding: 32px;
    }
    .card-head { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 24px; }
    .head-icon {
      width: 52px; height: 52px; border-radius: 14px; background: #ededf9;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .head-icon mat-icon { color: #5c6bc0; font-size: 26px; width: 26px; height: 26px; }
    .head-title { margin: 0 0 4px; font-size: 1.5rem; font-weight: 700; color: #1a1a2e; }
    .head-sub   { margin: 0; font-size: 0.875rem; color: #777; }
    .divider    { border: none; border-top: 1px solid #f0f0f0; margin: 0 0 28px; }

    .field { margin-bottom: 24px; }
    .field-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .field-label { font-size: 0.875rem; font-weight: 600; color: #333; }
    .required    { color: #6c63ff; }
    .tip-badge {
      display: flex; align-items: center; gap: 4px;
      background: #f5f0ff; color: #6c63ff;
      font-size: 0.75rem; padding: 4px 10px; border-radius: 20px;
    }
    .tip-icon { font-size: 14px; width: 14px; height: 14px; }
    .textarea {
      width: 100%; box-sizing: border-box; padding: 12px 16px;
      border: 1.5px solid #e8e8f0; border-radius: 10px;
      font-size: 0.9rem; font-family: inherit; line-height: 1.6;
      resize: vertical; color: #333; transition: border-color .2s, box-shadow .2s;
    }
    .textarea::placeholder { color: #bbb; }
    .textarea:focus { outline: none; border-color: #6c63ff; box-shadow: 0 0 0 3px rgba(108,99,255,0.12); }
    .textarea-footer { display: flex; justify-content: flex-end; margin-top: 4px; }
    .char-count { font-size: 0.75rem; color: #aaa; }

    .selects-row  { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
    .select-group { flex: 1; min-width: 160px; }
    .input-group  { flex: 1; min-width: 140px; }
    .adv-row { margin-top: 8px; }
    .select-label {
      display: flex; align-items: center; gap: 4px;
      font-size: 0.8rem; font-weight: 600; color: #555; margin-bottom: 6px;
    }
    .select-icon { font-size: 15px; width: 15px; height: 15px; color: #888; }
    .select-wrap { position: relative; }
    .select {
      width: 100%; appearance: none; -webkit-appearance: none;
      padding: 9px 36px 9px 12px;
      border: 1.5px solid #e8e8f0; border-radius: 8px;
      font-size: 0.875rem; font-family: inherit;
      background: #fff; color: #333; cursor: pointer;
      transition: border-color .2s, box-shadow .2s;
    }
    .select:focus { outline: none; border-color: #6c63ff; box-shadow: 0 0 0 3px rgba(108,99,255,0.12); }
    .chevron {
      position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
      font-size: 20px; color: #aaa; pointer-events: none;
    }
    .text-input {
      width: 100%; box-sizing: border-box; padding: 9px 12px;
      border: 1.5px solid #e8e8f0; border-radius: 8px;
      font-size: 0.875rem; font-family: inherit;
      transition: border-color .2s, box-shadow .2s;
    }
    .text-input:focus { outline: none; border-color: #6c63ff; box-shadow: 0 0 0 3px rgba(108,99,255,0.12); }

    .precall-card {
      display: flex; align-items: center; gap: 16px;
      padding: 16px 20px; margin-bottom: 20px;
      border-radius: 10px; background: #f8f8fc;
      border: 1.5px solid #e8e8f0; cursor: pointer;
    }
    .precall-check { width: 18px; height: 18px; accent-color: #6c63ff; flex-shrink: 0; cursor: pointer; }
    .precall-text  { flex: 1; }
    .precall-title { display: block; font-size: 0.875rem; font-weight: 600; color: #333; }
    .precall-desc  { display: block; font-size: 0.8rem; color: #777; margin-top: 2px; }
    .precall-info  { color: #bbb; font-size: 20px; }

    .advanced-panel {
      margin-bottom: 24px; border-radius: 10px !important;
      border: 1.5px solid #e8e8f0 !important; box-shadow: none !important;
    }

    .guardrail-warning {
      display: flex; align-items: center; gap: 10px;
      padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.875rem;
      background: #fff8e1; color: #e65100; border-left: 3px solid #ff9800;
    }
    .error-msg {
      padding: 10px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.875rem;
      background: #fce4ec; color: #c62828; border-left: 3px solid #e53935;
    }

    .form-actions { display: flex; justify-content: flex-end; margin-top: 8px; }
    .btn-primary {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 28px; border-radius: 10px;
      background: #5c6bc0; color: #fff;
      font-size: 0.9rem; font-weight: 600; border: none; cursor: pointer;
      transition: background .2s, box-shadow .2s;
      box-shadow: 0 2px 8px rgba(92,107,192,0.3);
    }
    .btn-primary:hover:not(:disabled) { background: #3f51b5; box-shadow: 0 4px 12px rgba(92,107,192,0.4); }
    .btn-primary:disabled { opacity: 0.55; cursor: not-allowed; box-shadow: none; }
    .btn-primary mat-icon { font-size: 18px; width: 18px; height: 18px; }

    /* ── Reference projects ───────────────────────────────────────────────── */
    .ref-section {
      border: 1.5px solid #e8e8f0; border-radius: 10px;
      padding: 16px 20px; margin-bottom: 20px;
    }
    .ref-section-head { margin-bottom: 12px; }
    .optional-tag { font-style: italic; color: #6c63ff; font-size: 0.875rem; }
    .ref-counter-row {
      display: flex; align-items: center; justify-content: space-between;
      background: #f8f8fc; border: 1.5px solid #e8e8f0; border-radius: 8px;
      padding: 10px 14px; margin-bottom: 12px;
    }
    .counter-ctrl { display: flex; align-items: center; gap: 6px; }
    .counter-val {
      min-width: 36px; text-align: center;
      font-size: 1rem; font-weight: 600; color: #1a1a2e;
    }
    .counter-btn {
      width: 28px; height: 28px; border-radius: 6px;
      border: 1.5px solid #d0d0e8; background: #fff;
      font-size: 1.1rem; font-weight: 700; color: #555;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: background .15s;
    }
    .counter-btn:hover:not(:disabled) { background: #ededfa; }
    .counter-btn:disabled { opacity: 0.35; cursor: not-allowed; }
    .counter-btn--add { border-color: #6c63ff; color: #6c63ff; }
    .counter-btn--add:hover:not(:disabled) { background: #f0eeff; }
    .ref-project {
      border-top: 1px solid #f0f0f0; padding-top: 12px; margin-top: 4px;
    }
    .ref-project-title {
      font-size: 0.8rem; font-weight: 700; font-style: italic; color: #5c6bc0;
      margin-bottom: 10px;
    }
    .ref-row { display: flex; gap: 12px; flex-wrap: wrap; }
    .ref-col { display: flex; flex-direction: column; }
    .ref-col--name { flex: 1.5; min-width: 140px; }
    .ref-col--desc { flex: 2.5; min-width: 180px; }
    .ref-col--num  { flex: 1; min-width: 110px; }
    .num-ctrl { display: flex; align-items: center; gap: 4px; }
    .num-input { flex: 1; min-width: 0; }

    /* ── Attachment drop-zone ─────────────────────────────────────────────── */
    .attach-zone {
      display: flex; flex-direction: column; align-items: center; gap: 4px;
      padding: 20px; border: 2px dashed #d0d0e8; border-radius: 10px;
      background: #fafafa; cursor: pointer; text-align: center;
      transition: border-color .2s, background .2s; outline: none;
    }
    .attach-zone:hover, .attach-zone:focus, .attach-zone--drag {
      border-color: #6c63ff; background: #f5f0ff;
    }
    .attach-icon { font-size: 32px; width: 32px; height: 32px; color: #8c87c2; margin-bottom: 4px; }
    .attach-label { font-size: 0.875rem; color: #555; }
    .attach-hint  { font-size: 0.75rem; color: #aaa; }

    .file-list  { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
    .file-chip  {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 8px;
      background: #f5f0ff; border: 1.5px solid #d8d2f8;
    }
    .file-icon  { font-size: 18px; width: 18px; height: 18px; color: #6c63ff; flex-shrink: 0; }
    .file-name  { flex: 1; font-size: 0.8rem; font-weight: 600; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-size  { font-size: 0.75rem; color: #888; flex-shrink: 0; }
    .file-remove {
      background: none; border: none; cursor: pointer; padding: 2px; color: #aaa;
      display: flex; align-items: center; border-radius: 4px; transition: color .15s, background .15s;
    }
    .file-remove:hover { color: #e53935; background: #fce4ec; }
    .file-remove mat-icon { font-size: 16px; width: 16px; height: 16px; }

    /* ── Inline result ────────────────────────────────────────────────────── */
    .inline-result {
      margin-top: 24px; border-radius: 12px;
      border: 1.5px solid #d8d2f8; background: #f8f7ff; overflow: hidden;
    }
    .inline-result-head {
      display: flex; align-items: center; gap: 10px;
      padding: 14px 20px; background: #ededf9;
      border-bottom: 1px solid #d8d2f8; font-size: 0.875rem; font-weight: 600; color: #3d3d7d;
    }
    .inline-result-head mat-icon { color: #6c63ff; font-size: 20px; width: 20px; height: 20px; }
    .inline-model {
      margin-left: auto; font-size: 0.75rem; color: #6c63ff;
      background: #e8e2ff; padding: 2px 10px; border-radius: 20px; font-weight: 400;
    }
    .inline-result-body {
      padding: 20px; font-size: 0.875rem; color: #333;
      white-space: pre-wrap; font-family: 'Courier New', monospace; line-height: 1.6;
      max-height: 480px; overflow-y: auto;
    }
    .inline-result-meta {
      display: flex; gap: 20px; padding: 10px 20px;
      border-top: 1px solid #d8d2f8; font-size: 0.75rem; color: #888; background: #f5f4ff;
    }
  `],
})
export class EstimationFormComponent {
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
  dragOver = signal(false);

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

  guardrailIcon(reason: GuardrailReason): string {
    return GUARDRAIL_ICONS[reason] ?? 'warning';
  }

  submit() {
    this.loading.set(true);
    this.error.set(null);
    this.guardrailError.set(null);
    this.inlineResult.set(null);

    if (this.attachments().length > 0) {
      this._submitWithAttachments();
    } else {
      this._submitJson();
    }
  }

  private _submitJson() {
    const validRefs = this.refProjects.filter(r => r.name.trim() && r.description.trim());
    this.form.reference_projects = validRefs.length > 0 ? validRefs : undefined;
    this.estimationService.create(this.form).subscribe({
      next: result => this.router.navigate(['/estimations', result.id]),
      error: (err: HttpErrorResponse) => this._handleError(err),
    });
  }

  private _submitWithAttachments() {
    this.estimationService.createSession().pipe(
      switchMap(({ session_id }) => {
        const fd = new FormData();
        fd.append('transcript', this.form.transcription);
        this.attachments().forEach(f => fd.append('attachments', f, f.name));
        if (this.form.model) fd.append('model', this.form.model);
        if (this.form.temperature != null) fd.append('temperature', String(this.form.temperature));
        fd.append('pre_call', String(this.form.pre_call ?? false));
        fd.append('output_format', this.form.output_format ?? 'phases_table');
        return this.estimationService.createWithAttachments(
          session_id, fd, this.form.prompt_version,
        );
      }),
    ).subscribe({
      next: result => {
        this.inlineResult.set(result);
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
