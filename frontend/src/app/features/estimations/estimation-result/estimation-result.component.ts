import { Component, Input, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatIconModule } from '@angular/material/icon';
import { DatePipe, DecimalPipe, NgClass, TitleCasePipe } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';
import { EstimationOut, EstimationService, EstimationStructuredResult, OutputFormat, SessionEstimationResponse } from '../estimation.service';

@Component({
  selector: 'app-estimation-result',
  standalone: true,
  imports: [
    RouterLink, MatProgressSpinnerModule, MatProgressBarModule, MatIconModule,
    DatePipe, DecimalPipe, NgClass, TitleCasePipe,
  ],
  template: `
    <div class="page" [class.page-inline]="inlineMarkdown || inlineLoading">
      @if (inlineLoading) {
        <div class="loading-wrap"><mat-spinner></mat-spinner></div>
      } @else if (inlineError) {
        <p class="not-found">{{ inlineError }}</p>
      } @else if (inlineMarkdown) {
        <div class="inline-container">
          <div class="title-row">
            <h1 class="page-title">Estimation Result</h1>
            <span class="status-badge status--completed">
              <mat-icon>check_circle</mat-icon>
              Completed
            </span>
          </div>

          <div class="meta-bar">
            <div class="meta-item">
              <div class="meta-icon mi--blue"><mat-icon>public</mat-icon></div>
              <div>
                <div class="meta-label">Model</div>
                <div class="meta-val">{{ inlineResponse?.model ?? '—' }}</div>
              </div>
            </div>
            <div class="meta-item">
              <div class="meta-icon mi--purple"><mat-icon>auto_awesome</mat-icon></div>
              <div>
                <div class="meta-label">Prompt</div>
                <div class="meta-val">{{ inlineResponse?.prompt_version ?? '—' }}</div>
              </div>
            </div>
            <div class="meta-item">
              <div class="meta-icon mi--indigo"><mat-icon>input</mat-icon></div>
              <div>
                <div class="meta-label">Input tokens</div>
                <div class="meta-val">{{ inlineResponse?.input_tokens != null ? (inlineResponse!.input_tokens | number) : '—' }}</div>
              </div>
            </div>
            <div class="meta-item">
              <div class="meta-icon mi--teal"><mat-icon>output</mat-icon></div>
              <div>
                <div class="meta-label">Output tokens</div>
                <div class="meta-val">{{ inlineResponse?.output_tokens != null ? (inlineResponse!.output_tokens | number) : '—' }}</div>
              </div>
            </div>
            <div class="meta-item">
              <div class="meta-icon mi--green"><mat-icon>attach_money</mat-icon></div>
              <div>
                <div class="meta-label">Cost</div>
                <div class="meta-val">{{ inlineResponse?.total_cost_usd != null ? ('$' + (inlineResponse!.total_cost_usd | number:'1.4-6')) : '—' }}</div>
              </div>
            </div>
            <div class="meta-item">
              <div class="meta-icon mi--orange"><mat-icon>calendar_today</mat-icon></div>
              <div>
                <div class="meta-label">Date</div>
                <div class="meta-val">{{ inlineRenderedAt | date:'medium' }}</div>
              </div>
            </div>
          </div>

          <div class="main-grid">
            <div class="main-col">
              <div class="content-card">
                <div class="content-card__head">
                  <div class="content-card__title">
                    <mat-icon>description</mat-icon> Estimation
                    <span class="format-badge format-badge--{{ effectiveFormat() }}">{{ effectiveFormat() | titlecase }}</span>
                  </div>
                  <button class="btn-copy" (click)="copyMarkdown()" [ngClass]="{ copied: copied() }">
                    <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
                    {{ copied() ? 'Copied!' : 'Copy' }}
                  </button>
                </div>
                <div [class]="formatClass()" [innerHTML]="renderMarkdown(inlineMarkdown)"></div>
              </div>

              @if (inlineResponse?.requirements) {
                <div class="content-card">
                  <div class="content-card__head">
                    <div class="content-card__title">
                      <mat-icon>list_alt</mat-icon> Extracted Requirements
                    </div>
                  </div>
                  <div class="md-render md-render--requirements" [innerHTML]="renderMarkdown(inlineResponse!.requirements)"></div>
                </div>
              }
            </div>

            <div class="sidebar">
              @if (teamMembers().length > 0) {
                <div class="sidebar-card">
                  <h3 class="sidebar-title"><mat-icon>group</mat-icon> Recommended Team</h3>
                  <ul class="team-list">
                    @for (member of teamMembers(); track member) {
                      <li class="team-item">
                        <mat-icon class="team-icon">person_outline</mat-icon>
                        <span>{{ member }}</span>
                      </li>
                    }
                  </ul>
                </div>
              }

              @if (durationWeeks()) {
                <div class="sidebar-card">
                  <h3 class="sidebar-title"><mat-icon>schedule</mat-icon> Estimated Duration</h3>
                  <div class="duration-display">
                    <span class="duration-num">{{ durationWeeks() }}</span>
                    <span class="duration-unit">weeks</span>
                  </div>
                </div>
              }

              @if (sidebarNotes().length > 0) {
                <div class="sidebar-card">
                  <h3 class="sidebar-title"><mat-icon>sticky_note_2</mat-icon> Notes</h3>
                  <ul class="notes-list">
                    @for (note of sidebarNotes(); track note) {
                      <li class="note-item">
                        <mat-icon class="note-icon">warning_amber</mat-icon>
                        <span>{{ note }}</span>
                      </li>
                    }
                  </ul>
                </div>
              }
            </div>
          </div>

          @if (validation()) {
            <div class="validation-section">
              <div class="validation-head">
                <div class="validation-title">
                  <mat-icon [ngClass]="validationIconClass()">{{ validationIcon() }}</mat-icon>
                  Output Validation
                </div>
                <span class="validation-score-label">
                  Structure score: {{ (validation()!.score * 100) | number:'1.0-0' }}%
                </span>
              </div>

              <mat-progress-bar
                mode="determinate"
                [value]="validation()!.score * 100"
                [color]="validationBarColor()">
              </mat-progress-bar>

              <div class="checks-grid">
                <div class="check-item" [ngClass]="{ ok: validation()!.has_title, fail: !validation()!.has_title }">
                  <mat-icon>{{ validation()!.has_title ? 'check_circle' : 'cancel' }}</mat-icon><span>Title</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_breakdown_table, fail: !validation()!.has_breakdown_table }">
                  <mat-icon>{{ validation()!.has_breakdown_table ? 'check_circle' : 'cancel' }}</mat-icon><span>Breakdown table</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_totals_section, fail: !validation()!.has_totals_section }">
                  <mat-icon>{{ validation()!.has_totals_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Totals section</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_team_section, fail: !validation()!.has_team_section }">
                  <mat-icon>{{ validation()!.has_team_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Team section</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_duration_section, fail: !validation()!.has_duration_section }">
                  <mat-icon>{{ validation()!.has_duration_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Duration</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.finish_reason_ok, fail: !validation()!.finish_reason_ok }">
                  <mat-icon>{{ validation()!.finish_reason_ok ? 'check_circle' : 'cancel' }}</mat-icon><span>Complete response</span>
                </div>
              </div>
            </div>
          }
        </div>
      } @else if (loading()) {
        <div class="loading-wrap"><mat-spinner></mat-spinner></div>
      } @else if (estimation()) {

        <!-- Page header -->
        <div class="page-header">
          <a routerLink="/estimations" class="back-link">
            <mat-icon>arrow_back</mat-icon> Back to history
          </a>
          <div class="title-row">
            <h1 class="page-title">Estimation Result</h1>
            <span class="status-badge" [ngClass]="'status--' + estimation()!.status">
              <mat-icon>{{ estimation()!.status === 'completed' ? 'check_circle' : estimation()!.status === 'failed' ? 'error' : 'pending' }}</mat-icon>
              {{ estimation()!.status | titlecase }}
            </span>
          </div>
        </div>

        <!-- Meta bar -->
        <div class="meta-bar">
          <div class="meta-item">
            <div class="meta-icon mi--blue"><mat-icon>public</mat-icon></div>
            <div>
              <div class="meta-label">Model</div>
              <div class="meta-val">{{ estimation()!.model_used ?? '—' }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon mi--purple"><mat-icon>auto_awesome</mat-icon></div>
            <div>
              <div class="meta-label">Prompt</div>
              <div class="meta-val">{{ estimation()!.prompt_version ?? '—' }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon mi--indigo"><mat-icon>input</mat-icon></div>
            <div>
              <div class="meta-label">Input tokens</div>
              <div class="meta-val">{{ estimation()!.input_tokens != null ? (estimation()!.input_tokens! | number) : '—' }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon mi--teal"><mat-icon>output</mat-icon></div>
            <div>
              <div class="meta-label">Output tokens</div>
              <div class="meta-val">{{ estimation()!.output_tokens != null ? (estimation()!.output_tokens! | number) : '—' }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon mi--green"><mat-icon>attach_money</mat-icon></div>
            <div>
              <div class="meta-label">Cost</div>
              <div class="meta-val">{{ estimation()!.total_cost_usd != null ? ('$' + (estimation()!.total_cost_usd! | number:'1.4-6')) : '—' }}</div>
            </div>
          </div>
          <div class="meta-item">
            <div class="meta-icon mi--orange"><mat-icon>calendar_today</mat-icon></div>
            <div>
              <div class="meta-label">Date</div>
              <div class="meta-val">{{ estimation()!.created_at | date:'medium' }}</div>
            </div>
          </div>
        </div>

        <!-- Main two-column layout -->
        <div class="main-grid">

          <!-- Left: estimation content -->
          <div class="main-col">
            @if (estimation()!.estimation_markdown) {
              <div class="content-card">
                <div class="content-card__head">
                  <div class="content-card__title">
                    <mat-icon>description</mat-icon> Estimation
                    <span class="format-badge format-badge--{{ effectiveFormat() }}">{{ effectiveFormat() | titlecase }}</span>
                  </div>
                  <button class="btn-copy" (click)="copyMarkdown()" [ngClass]="{ copied: copied() }">
                    <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
                    {{ copied() ? 'Copied!' : 'Copy' }}
                  </button>
                </div>
                <div [class]="formatClass()" [innerHTML]="renderMarkdown(estimation()!.estimation_markdown)"></div>
              </div>
            }

            @if (estimation()!.requirements) {
              <div class="content-card">
                <div class="content-card__head">
                  <div class="content-card__title">
                    <mat-icon>list_alt</mat-icon> Extracted Requirements
                  </div>
                </div>
                <div class="md-render md-render--requirements" [innerHTML]="renderMarkdown(estimation()!.requirements)"></div>
              </div>
            }
          </div>

          <!-- Right: sidebar -->
          <div class="sidebar">

            @if (teamMembers().length > 0) {
              <div class="sidebar-card">
                <h3 class="sidebar-title"><mat-icon>group</mat-icon> Recommended Team</h3>
                <ul class="team-list">
                  @for (member of teamMembers(); track member) {
                    <li class="team-item">
                      <mat-icon class="team-icon">person_outline</mat-icon>
                      <span>{{ member }}</span>
                    </li>
                  }
                </ul>
              </div>
            }

            @if (durationWeeks()) {
              <div class="sidebar-card">
                <h3 class="sidebar-title"><mat-icon>schedule</mat-icon> Estimated Duration</h3>
                <div class="duration-display">
                  <span class="duration-num">{{ durationWeeks() }}</span>
                  <span class="duration-unit">weeks</span>
                </div>
              </div>
            }

            @if (sidebarNotes().length > 0) {
              <div class="sidebar-card">
                <h3 class="sidebar-title"><mat-icon>sticky_note_2</mat-icon> Notes</h3>
                <ul class="notes-list">
                  @for (note of sidebarNotes(); track note) {
                    <li class="note-item">
                      <mat-icon class="note-icon">warning_amber</mat-icon>
                      <span>{{ note }}</span>
                    </li>
                  }
                </ul>
              </div>
            }

            @if (phases().length > 0) {
              <div class="sidebar-card">
                <h3 class="sidebar-title"><mat-icon>layers</mat-icon> Phases</h3>
                <div class="phases-list">
                  @for (phase of phases(); track phase.name) {
                    <div class="phase-item">
                      <div class="phase-name">{{ phase.name }}</div>
                      <div class="phase-meta">
                        <span>{{ phase.duration_weeks }}w</span>
                        <span class="phase-cost">{{ phase.cost_eur | number:'1.0-0' }} EUR</span>
                      </div>
                    </div>
                  }
                </div>
              </div>
            }

          </div>
        </div>

        <!-- Validation section -->
        @if (validation()) {
          <div class="validation-section">
            <div class="validation-head">
              <div class="validation-title">
                <mat-icon [ngClass]="validationIconClass()">{{ validationIcon() }}</mat-icon>
                Output Validation
              </div>
              <span class="validation-score-label">
                Structure score: {{ (validation()!.score * 100) | number:'1.0-0' }}%
              </span>
            </div>

            <mat-progress-bar
              mode="determinate"
              [value]="validation()!.score * 100"
              [color]="validationBarColor()">
            </mat-progress-bar>

            <div class="checks-grid">
              <div class="check-item" [ngClass]="{ ok: validation()!.has_title, fail: !validation()!.has_title }">
                <mat-icon>{{ validation()!.has_title ? 'check_circle' : 'cancel' }}</mat-icon><span>Title</span>
              </div>
              <div class="check-item" [ngClass]="{ ok: validation()!.has_breakdown_table, fail: !validation()!.has_breakdown_table }">
                <mat-icon>{{ validation()!.has_breakdown_table ? 'check_circle' : 'cancel' }}</mat-icon><span>Breakdown table</span>
              </div>
              <div class="check-item" [ngClass]="{ ok: validation()!.has_totals_section, fail: !validation()!.has_totals_section }">
                <mat-icon>{{ validation()!.has_totals_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Totals section</span>
              </div>
              <div class="check-item" [ngClass]="{ ok: validation()!.has_team_section, fail: !validation()!.has_team_section }">
                <mat-icon>{{ validation()!.has_team_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Team section</span>
              </div>
              <div class="check-item" [ngClass]="{ ok: validation()!.has_duration_section, fail: !validation()!.has_duration_section }">
                <mat-icon>{{ validation()!.has_duration_section ? 'check_circle' : 'cancel' }}</mat-icon><span>Duration</span>
              </div>
              <div class="check-item" [ngClass]="{ ok: validation()!.finish_reason_ok, fail: !validation()!.finish_reason_ok }">
                <mat-icon>{{ validation()!.finish_reason_ok ? 'check_circle' : 'cancel' }}</mat-icon><span>Complete response</span>
              </div>
            </div>

            @if (validation()!.declared_total_hours !== null || validation()!.sum_row_hours !== null ||
                 validation()!.declared_total_cost !== null || validation()!.sum_row_cost !== null) {
              <div class="numeric-checks">
                @if (validation()!.declared_total_hours !== null || validation()!.sum_row_hours !== null) {
                  <div class="numeric-check" [ngClass]="{ ok: validation()!.hours_match === true, fail: validation()!.hours_match === false }">
                    <mat-icon>{{ validation()!.hours_match === true ? 'check_circle' : validation()!.hours_match === false ? 'cancel' : 'help_outline' }}</mat-icon>
                    <span>Hours: {{ validation()!.declared_total_hours ?? '—' }} declared / {{ validation()!.sum_row_hours ?? '—' }} rows</span>
                  </div>
                }
                @if (validation()!.declared_total_cost !== null || validation()!.sum_row_cost !== null) {
                  <div class="numeric-check" [ngClass]="{ ok: validation()!.cost_match === true, fail: validation()!.cost_match === false }">
                    <mat-icon>{{ validation()!.cost_match === true ? 'check_circle' : validation()!.cost_match === false ? 'cancel' : 'help_outline' }}</mat-icon>
                    <span>Cost: {{ (validation()!.declared_total_cost | number:'1.0-0') ?? '—' }} declared / {{ (validation()!.sum_row_cost | number:'1.0-0') ?? '—' }} rows</span>
                  </div>
                }
              </div>
            }

            @if (validation()!.issues.length > 0) {
              <div class="issues-list">
                @for (issue of validation()!.issues; track issue) {
                  <div class="issue-item">
                    <mat-icon class="issue-icon">warning</mat-icon> {{ issue }}
                  </div>
                }
              </div>
            }
          </div>
        }

      } @else {
        <p class="not-found">Estimation not found.</p>
      }
    </div>
  `,
  styles: [`
    /* ── Page ─────────────────────────────────────────────────────────────── */
    .page { 
      max-width: 100%; 
      width: 100%;
      margin: 0; 
      padding: 0;
    }
    .page-inline { 
      max-width: 100%; 
      margin: 0; 
      padding: 0; 
    }
    .inline-container { display: flex; flex-direction: column; gap: 16px; width: 100%; }
    .loading-wrap { display: flex; justify-content: center; padding: 80px; }
    .not-found { color: #666; text-align: center; padding: 60px; }

    /* ── Header ───────────────────────────────────────────────────────────── */
    .back-link {
      display: inline-flex; align-items: center; gap: 4px;
      color: #5c6bc0; font-size: 0.8rem; text-decoration: none; margin-bottom: 14px;
      font-weight: 500;
    }
    .back-link:hover { text-decoration: underline; }
    .back-link mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .title-row { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
    .page-title { margin: 0; font-size: 1.6rem; font-weight: 700; color: #1a1a2e; }
    .status-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 5px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;
    }
    .status-badge mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .status--completed { background: #e8f5e9; color: #2e7d32; }
    .status--failed    { background: #fce4ec; color: #c62828; }
    .status--pending, .status--processing { background: #e3f2fd; color: #1565c0; }

    /* ── Meta bar ─────────────────────────────────────────────────────────── */
    .meta-bar {
      display: flex; flex-wrap: wrap; gap: 12px;
      background: #fff; border-radius: 12px; border: 1px solid #eee;
      padding: 12px 16px; margin-bottom: 20px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .meta-item { display: flex; align-items: center; gap: 8px; flex: 0 1 calc(16.666% - 10px); min-width: 100px; }
    .meta-icon {
      width: 32px; height: 32px; border-radius: 6px;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .meta-icon mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .mi--blue   { background: #c5d9f8; } .mi--blue mat-icon   { color: #1565c0; }
    .mi--purple { background: #e6d7f0; } .mi--purple mat-icon { color: #7b1fa2; }
    .mi--indigo { background: #d5cce3; } .mi--indigo mat-icon { color: #283593; }
    .mi--teal   { background: #d0e8e5; } .mi--teal mat-icon   { color: #00695c; }
    .mi--green  { background: #c8e6c9; } .mi--green mat-icon  { color: #2e7d32; }
    .mi--orange { background: #f5dcc0; } .mi--orange mat-icon { color: #e65100; }
    .meta-label { font-size: 0.65rem; color: #888; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 500; }
    .meta-val   { font-size: 0.85rem; font-weight: 600; color: #1a1a2e; }

    /* ── Two-column grid ──────────────────────────────────────────────────── */
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 320px;
      gap: 24px;
      margin-bottom: 24px;
      align-items: start;
    }
    @media (max-width: 800px) {
      .main-grid { grid-template-columns: 1fr; }
    }

    /* ── Content card ─────────────────────────────────────────────────────── */
    .main-col { display: flex; flex-direction: column; gap: 16px; }
    .content-card {
      background: #fff; border-radius: 12px; border: 1px solid #eee;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04); overflow: hidden;
      width: 100%;
    }
    .inline-container .content-card {
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      border-color: #e0e0e8;
    }
    .content-card__head {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; border-bottom: 1px solid #f5f5f5; background: #fafbfc;
    }
    .content-card__title {
      display: flex; align-items: center; gap: 8px;
      font-size: 0.95rem; font-weight: 700; color: #1a1a2e;
    }
    .content-card__title mat-icon { color: #5c6bc0; font-size: 18px; width: 18px; height: 18px; }
    .btn-copy {
      display: flex; align-items: center; gap: 5px;
      padding: 5px 12px; border-radius: 6px;
      background: #f0f0f8; border: 1px solid #d5d9f5;
      font-size: 0.75rem; font-weight: 600; color: #5c6bc0; cursor: pointer;
      transition: background .15s, border-color .15s;
    }
    .btn-copy:hover { background: #e8e5f5; border-color: #c5cbe8; }
    .btn-copy.copied { background: #e8f5e9; color: #2e7d32; border-color: #a5d6a7; }
    .btn-copy mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .markdown-pre {
      padding: 14px 16px; margin: 0; overflow-x: auto; overflow-y: auto; max-height: 420px;
      white-space: pre-wrap; font-family: 'Monaco', 'Courier New', monospace; font-size: 0.78rem; line-height: 1.5; color: #333;
      background: #fafbfc;
    }

    /* ── Markdown rendered content ────────────────────────────────────────── */
    .md-render {
      padding: 16px 20px; overflow-x: auto; max-height: 600px; overflow-y: auto;
      font-size: 0.88rem; line-height: 1.65; color: #2d2d3f; background: #fafbfc;
    }

    /* Common markdown elements */
    .md-render :is(h1, h2, h3, h4) {
      color: #1a1a2e; font-weight: 700; margin: 1rem 0 0.4rem;
    }
    .md-render h1 { font-size: 1.2rem; border-bottom: 2px solid #e8e8f0; padding-bottom: 6px; }
    .md-render h2 { font-size: 1.05rem; border-bottom: 1px solid #eee; padding-bottom: 4px; }
    .md-render h3 { font-size: 0.95rem; color: #3c3c5c; }
    .md-render p  { margin: 0.5rem 0; }
    .md-render ul, .md-render ol { padding-left: 1.4rem; margin: 0.4rem 0; }
    .md-render li { margin: 0.2rem 0; }
    .md-render strong { color: #1a1a2e; }
    .md-render code {
      background: #ebebf5; border-radius: 4px; padding: 1px 5px;
      font-family: 'Monaco', 'Courier New', monospace; font-size: 0.82em; color: #5c3e9d;
    }
    .md-render pre {
      background: #1e1e2e; border-radius: 8px; padding: 12px 16px;
      overflow-x: auto; margin: 0.8rem 0;
    }
    .md-render pre code { background: none; color: #cdd6f4; padding: 0; font-size: 0.8rem; }
    .md-render blockquote {
      border-left: 3px solid #5c6bc0; margin: 0.8rem 0; padding: 4px 12px;
      background: #f0f0fa; color: #555; border-radius: 0 6px 6px 0;
    }
    .md-render hr { border: none; border-top: 1px solid #e8e8f0; margin: 1rem 0; }

    /* ── Table styles (phases_table & line_items) ─────────────────────────── */
    .md-render table {
      width: 100%; border-collapse: collapse; font-size: 0.83rem;
      margin: 0.8rem 0; border-radius: 8px; overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .md-render th {
      background: #5c6bc0; color: #fff; padding: 9px 12px;
      text-align: left; font-weight: 600; font-size: 0.78rem;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    .md-render td {
      padding: 8px 12px; border-bottom: 1px solid #eee;
      vertical-align: top; color: #333;
    }
    .md-render tr:last-child td { border-bottom: none; }
    .md-render tr:nth-child(even) td { background: #f8f8fc; }
    .md-render tr:hover td { background: #f0f0fa; transition: background 0.1s; }

    /* Highlight totals / subtotals rows (rows with bold cells) */
    .md-render td strong { color: #1a1a2e; }
    .md-render tr:has(td strong:first-child) td {
      background: #ededf8 !important; font-weight: 600; color: #1a1a2e;
    }

    /* ── phases_table specific ────────────────────────────────────────────── */
    .md-render--phases-table h2 { color: #5c6bc0; margin-top: 1.2rem; }
    .md-render--phases-table h3 { color: #7986cb; }

    /* ── line_items specific ──────────────────────────────────────────────── */
    .md-render--line-items table th:last-child,
    .md-render--line-items table td:last-child { text-align: right; }

    /* ── narrative specific ───────────────────────────────────────────────── */
    .md-render--narrative {
      font-size: 0.93rem; line-height: 1.8; color: #2c2c3e;
      background: #fff; max-height: none;
    }
    .md-render--narrative p { margin: 0.8rem 0; text-align: justify; }
    .md-render--narrative h2 {
      font-size: 1.1rem; color: #3c3c6e; margin-top: 1.4rem;
      border-bottom: 1px solid #dde; padding-bottom: 6px;
    }
    .md-render--narrative h3 { font-size: 1rem; color: #555; }

    /* ── requirements (reqs from pre-call) ───────────────────────────────── */
    .md-render--requirements {
      font-size: 0.85rem; max-height: 300px;
    }
    .md-render--requirements li { margin: 0.3rem 0; }

    /* ── Format badge ─────────────────────────────────────────────────────── */
    .format-badge {
      display: inline-flex; align-items: center;
      padding: 2px 8px; border-radius: 10px; font-size: 0.68rem;
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
      margin-left: 6px;
    }
    .format-badge--phases_table { background: #e8eaf6; color: #3949ab; }
    .format-badge--line_items   { background: #e8f5e9; color: #2e7d32; }
    .format-badge--narrative    { background: #fff3e0; color: #e65100; }

    /* ── Sidebar ──────────────────────────────────────────────────────────── */
    .sidebar { display: flex; flex-direction: column; gap: 12px; }
    .sidebar-card {
      background: #fff; border-radius: 12px; border: 1px solid #eee;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04); padding: 14px 16px;
    }
    .sidebar-title {
      display: flex; align-items: center; gap: 8px;
      margin: 0 0 10px; font-size: 0.85rem; font-weight: 700; color: #1a1a2e;
    }
    .sidebar-title mat-icon { font-size: 16px; width: 16px; height: 16px; color: #5c6bc0; }

    .team-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
    .team-item {
      display: flex; align-items: center; gap: 10px; padding: 8px 10px; font-size: 0.8rem; color: #555;
      background: #fafbff; border-radius: 8px;
    }
    .team-item:hover { background: #f5f0ff; }
    .team-icon {
      font-size: 16px; width: 16px; height: 16px; flex-shrink: 0;
      background: #5c6bc0; color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center;
      padding: 2px;
    }
    .team-icon mat-icon { font-size: 10px; width: 10px; height: 10px; }

    .duration-display { display: flex; align-items: baseline; gap: 8px; }
    .duration-num  { font-size: 2.2rem; font-weight: 700; color: #1a1a2e; }
    .duration-unit { font-size: 0.9rem; color: #888; font-weight: 400; }

    .notes-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
    .note-item  { display: flex; align-items: flex-start; gap: 8px; font-size: 0.75rem; color: #555; line-height: 1.4; }
    .note-icon  { font-size: 14px; width: 14px; height: 14px; color: #ff9800; flex-shrink: 0; margin-top: 2px; }

    .phases-list { display: flex; flex-direction: column; gap: 6px; }
    .phase-item  { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 0.75rem; }
    .phase-item:last-child { border-bottom: none; padding-bottom: 0; }
    .phase-name  { font-weight: 600; color: #333; }
    .phase-meta  { display: flex; gap: 8px; color: #888; }
    .phase-cost  { font-weight: 600; color: #5c6bc0; }

    /* ── Validation section ───────────────────────────────────────────────── */
    .validation-section {
      background: #fff; border-radius: 12px; border: 1px solid #eee;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04); padding: 16px 20px;
    }
    .validation-head {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
    }
    .validation-title {
      display: flex; align-items: center; gap: 8px;
      font-size: 0.95rem; font-weight: 700; color: #1a1a2e;
    }
    .validation-title mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .validation-score-label { font-size: 0.8rem; color: #888; }
    mat-progress-bar { margin: 10px 0 14px; height: 6px; border-radius: 3px; }

    .checks-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .check-item {
      display: flex; align-items: center; gap: 5px;
      font-size: 0.75rem; padding: 5px 10px;
      background: #f5f5f5; border-radius: 16px; color: #555;
    }
    .check-item.ok   { background: rgba(76,175,80,0.12); color: #2e7d32; }
    .check-item.fail { background: rgba(244,67,54,0.12); color: #c62828; }
    .check-item.ok   mat-icon { color: #4caf50; font-size: 14px; width: 14px; height: 14px; }
    .check-item.fail mat-icon { color: #f44336; font-size: 14px; width: 14px; height: 14px; }

    .numeric-checks { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .numeric-check {
      display: flex; align-items: center; gap: 5px;
      font-size: 0.75rem; padding: 5px 10px; border-radius: 6px;
      background: #f5f5f5; color: #666;
    }
    .numeric-check.ok   { background: rgba(76,175,80,0.12); color: #2e7d32; }
    .numeric-check.ok   mat-icon { color: #4caf50; font-size: 14px; width: 14px; height: 14px; }
    .numeric-check.fail { background: rgba(244,67,54,0.12); color: #c62828; }
    .numeric-check.fail mat-icon { color: #f44336; font-size: 14px; width: 14px; height: 14px; }

    .issues-list { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
    .issue-item {
      display: flex; align-items: flex-start; gap: 8px;
      font-size: 0.75rem; color: #e65100; padding: 8px 12px;
      background: #fff8e1; border-radius: 6px; line-height: 1.4;
    }
    .issue-icon { font-size: 14px; color: #ff9800; flex-shrink: 0; margin-top: 2px; }

    .icon-ok   { color: #4caf50; }
    .icon-warn { color: #ff9800; }
    .icon-fail { color: #f44336; }
  `],
})
export class EstimationResultComponent implements OnInit {
  @Input() inlineMarkdown: string | null = null;
  @Input() inlineResponse: SessionEstimationResponse | null = null;
  @Input() inlineLoading = false;
  @Input() inlineError: string | null = null;
  @Input() outputFormat: OutputFormat | null = null;

  estimation = signal<EstimationOut | null>(null);
  loading    = signal(false);
  copied     = signal(false);
  inlineRenderedAt = new Date();

  /** Determine effective output format: explicit input → response field → stored estimation → default */
  effectiveFormat = computed<OutputFormat>(() => {
    return this.outputFormat
      ?? this.inlineResponse?.output_format
      ?? this.estimation()?.output_format
      ?? 'phases_table';
  });

  /** Render markdown string to safe HTML via marked */
  renderMarkdown(text: string | null | undefined): SafeHtml {
    if (!text) return this.sanitizer.bypassSecurityTrustHtml('');
    const html = marked.parse(text, { async: false }) as string;
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  /** CSS class for the rendered content area based on output format */
  formatClass = computed<string>(() => {
    const f = this.effectiveFormat();
    return `md-render md-render--${f.replace('_', '-')}`;
  });

  validation = () => this.inlineResponse?.validation ?? this.estimation()?.validation_result ?? null;

  statusColor = () => this.estimation()?.status === 'completed' ? 'primary' : 'warn';

  private currentStructuredResult(): EstimationStructuredResult | null {
    return (this.inlineResponse?.structured_result as EstimationStructuredResult | null)
      ?? (this.estimation()?.structured_result as EstimationStructuredResult | null)
      ?? null;
  }

  private currentMarkdown(): string {
    return this.inlineMarkdown ?? this.estimation()?.estimation_markdown ?? '';
  }

  /** Duration from structured_result, fallback to markdown parsing. */
  durationWeeks = computed(() => {
    const sr = this.currentStructuredResult();
    if (sr?.total_duration_weeks) return sr.total_duration_weeks;
    const md = this.currentMarkdown();
    const m = /(\d+)\s+week/i.exec(md);
    return m ? Number.parseInt(m[1], 10) : null;
  });

  /** Phase list from structured_result. */
  phases = computed(() => {
    const sr = this.currentStructuredResult();
    return sr?.phases ?? [];
  });

  /** Team members extracted from the markdown "Team" section. */
  teamMembers = computed(() => {
    const md = this.currentMarkdown();
    return this.extractBulletSection(md, /^#{1,4}\s+.*\bteam\b/i);
  });

  /** Notes extracted from the markdown "Notes" or phase assumptions. */
  sidebarNotes = computed(() => {
    const md = this.currentMarkdown();
    const fromMd = this.extractBulletSection(md, /^#{1,4}\s+.*\bnotes?\b/i);
    if (fromMd.length > 0) return fromMd;
    // Fallback: collect assumptions from structured_result phases
    const phases = this.phases();
    return phases.flatMap(p => p.assumptions ?? []).slice(0, 5);
  });

  /** Extract bullet-list items from the first matching section in markdown. */
  private extractBulletSection(markdown: string, headerPattern: RegExp): string[] {
    const lines = markdown.split('\n');
    let inSection = false;
    let headerLevel = 0;
    const items: string[] = [];

    for (const line of lines) {
      const headerMatch = /^(#{1,4})\s+(.+)$/.exec(line);
      if (headerMatch) {
        const level = headerMatch[1].length;
        if (!inSection && headerPattern.test(line)) {
          inSection = true;
          headerLevel = level;
          continue;
        }
        if (inSection && level <= headerLevel) break;
      }
      if (inSection && /^\s*[-*]\s+/.test(line)) {
        items.push(line.replace(/^\s*[-*]\s+/, '').trim());
      }
    }
    return items;
  }

  validationIcon(): string {
    const v = this.validation();
    if (!v) return 'help';
    if (v.score === 1) return 'verified';
    if (v.score >= 0.75) return 'check_circle';
    return 'warning';
  }

  validationIconClass(): Record<string, boolean> {
    const v = this.validation();
    if (!v) return {};
    return {
      'icon-ok':   v.score >= 0.75,
      'icon-warn': v.score >= 0.5 && v.score < 0.75,
      'icon-fail': v.score < 0.5,
    };
  }

  validationBarColor(): 'primary' | 'warn' {
    const v = this.validation();
    if (!v) return 'primary';
    return v.score >= 0.75 ? 'primary' : 'warn';
  }

  copyMarkdown() {
    const md = this.estimation()?.estimation_markdown ?? this.inlineMarkdown ?? '';
    navigator.clipboard.writeText(md).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 2000);
    });
  }

  constructor(
    private readonly estimationService: EstimationService,
    private readonly route: ActivatedRoute,
    private readonly sanitizer: DomSanitizer,
  ) {}

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.loading.set(false);
      return;
    }

    this.loading.set(true);
    this.estimationService.get(id).subscribe({
      next: e => { this.estimation.set(e); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
