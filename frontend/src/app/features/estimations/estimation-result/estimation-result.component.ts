import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatIconModule } from '@angular/material/icon';
import { DatePipe, DecimalPipe, NgClass } from '@angular/common';
import { EstimationOut, EstimationService } from '../estimation.service';

@Component({
  selector: 'app-estimation-result',
  standalone: true,
  imports: [
    RouterLink,
    MatCardModule, MatButtonModule, MatChipsModule, MatDividerModule,
    MatProgressSpinnerModule, MatProgressBarModule, MatIconModule,
    DatePipe, DecimalPipe, NgClass,
  ],
  template: `
    <div class="result-page">
      @if (loading()) {
        <mat-spinner></mat-spinner>
      } @else if (estimation()) {
        <div class="result-header">
          <h2>Estimation Result</h2>
          <mat-chip-set>
            <mat-chip [color]="statusColor()">{{ estimation()!.status }}</mat-chip>
          </mat-chip-set>
          <a mat-button routerLink="/estimations">← Back to history</a>
        </div>

        <mat-card class="meta-card">
          <mat-card-content>
            <div class="meta-row">
              <span>Model: <strong>{{ estimation()!.model_used ?? '—' }}</strong></span>
              <span>Prompt: <strong>{{ estimation()!.prompt_version ?? '—' }}</strong></span>
              <span>Input tokens: <strong>{{ estimation()!.input_tokens ?? '—' }}</strong></span>
              <span>Output tokens: <strong>{{ estimation()!.output_tokens ?? '—' }}</strong></span>
              <span>Cost: <strong>\${{ estimation()!.total_cost_usd | number:'1.4-6' }}</strong></span>
              <span>Date: <strong>{{ estimation()!.created_at | date:'medium' }}</strong></span>
            </div>
          </mat-card-content>
        </mat-card>

        @if (estimation()!.estimation_markdown) {
          <mat-card class="markdown-card">
            <mat-card-header><mat-card-title>Estimation</mat-card-title></mat-card-header>
            <mat-card-content>
              <pre class="markdown-pre">{{ estimation()!.estimation_markdown }}</pre>
            </mat-card-content>
          </mat-card>
        }

        @if (estimation()!.requirements) {
          <mat-card>
            <mat-card-header><mat-card-title>Extracted Requirements</mat-card-title></mat-card-header>
            <mat-card-content>
              <pre class="markdown-pre">{{ estimation()!.requirements }}</pre>
            </mat-card-content>
          </mat-card>
        }

        @if (validation()) {
          <mat-card class="validation-card">
            <mat-card-header>
              <mat-card-title>
                <mat-icon [ngClass]="validationIconClass()">{{ validationIcon() }}</mat-icon>
                Output Validation
              </mat-card-title>
              <mat-card-subtitle>Structure score: {{ (validation()!.score * 100) | number:'1.0-0' }}%</mat-card-subtitle>
            </mat-card-header>
            <mat-card-content>
              <mat-progress-bar
                mode="determinate"
                [value]="validation()!.score * 100"
                [color]="validationBarColor()">
              </mat-progress-bar>

              <div class="checks-grid">
                <div class="check-item" [ngClass]="{ ok: validation()!.has_title, fail: !validation()!.has_title }">
                  <mat-icon>{{ validation()!.has_title ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Title</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_breakdown_table, fail: !validation()!.has_breakdown_table }">
                  <mat-icon>{{ validation()!.has_breakdown_table ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Breakdown table</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_totals_section, fail: !validation()!.has_totals_section }">
                  <mat-icon>{{ validation()!.has_totals_section ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Totals section</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_team_section, fail: !validation()!.has_team_section }">
                  <mat-icon>{{ validation()!.has_team_section ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Team section</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.has_duration_section, fail: !validation()!.has_duration_section }">
                  <mat-icon>{{ validation()!.has_duration_section ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Duration</span>
                </div>
                <div class="check-item" [ngClass]="{ ok: validation()!.finish_reason_ok, fail: !validation()!.finish_reason_ok }">
                  <mat-icon>{{ validation()!.finish_reason_ok ? 'check_circle' : 'cancel' }}</mat-icon>
                  <span>Complete response</span>
                </div>
                @if (validation()!.hours_match !== null) {
                  <div class="check-item" [ngClass]="{ ok: validation()!.hours_match, fail: !validation()!.hours_match }">
                    <mat-icon>{{ validation()!.hours_match ? 'check_circle' : 'cancel' }}</mat-icon>
                    <span>Hours match</span>
                  </div>
                }
                @if (validation()!.cost_match !== null) {
                  <div class="check-item" [ngClass]="{ ok: validation()!.cost_match, fail: !validation()!.cost_match }">
                    <mat-icon>{{ validation()!.cost_match ? 'check_circle' : 'cancel' }}</mat-icon>
                    <span>Cost match</span>
                  </div>
                }
              </div>

              @if (validation()!.issues.length > 0) {
                <mat-divider></mat-divider>
                <ul class="issues-list">
                  @for (issue of validation()!.issues; track issue) {
                    <li><mat-icon class="issue-icon">warning</mat-icon>{{ issue }}</li>
                  }
                </ul>
              }
            </mat-card-content>
          </mat-card>
        }
      } @else {
        <p>Estimation not found.</p>
      }
    </div>
  `,
  styles: [`
    .result-page { max-width:900px; margin:24px auto; }
    .result-header { display:flex; align-items:center; gap:16px; margin-bottom:16px; }
    .meta-card { margin-bottom:16px; }
    .meta-row { display:flex; flex-wrap:wrap; gap:16px; }
    .markdown-card { margin-bottom:16px; }
    .markdown-pre { white-space:pre-wrap; font-family:inherit; font-size:0.9rem; }
    .validation-card { margin-top:16px; }
    .validation-card mat-card-title { display:flex; align-items:center; gap:8px; }
    mat-progress-bar { margin:12px 0 16px; }
    .checks-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:8px; margin-bottom:12px; }
    .check-item { display:flex; align-items:center; gap:6px; font-size:0.85rem; }
    .check-item.ok mat-icon { color:#4caf50; font-size:18px; }
    .check-item.fail mat-icon { color:#f44336; font-size:18px; }
    .issues-list { margin:12px 0 0; padding:0; list-style:none; }
    .issues-list li { display:flex; align-items:center; gap:6px; font-size:0.85rem; color:#e65100; margin-bottom:4px; }
    .issue-icon { font-size:16px; color:#ff9800; }
    .icon-ok { color:#4caf50; }
    .icon-warn { color:#ff9800; }
    .icon-fail { color:#f44336; }
  `],
})
export class EstimationResultComponent implements OnInit {
  estimation = signal<EstimationOut | null>(null);
  loading = signal(true);
  statusColor = () => this.estimation()?.status === 'completed' ? 'primary' : 'warn';

  validation = () => this.estimation()?.validation_result ?? null;

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
      'icon-ok': v.score === 1,
      'icon-warn': v.score >= 0.75 && v.score < 1,
      'icon-fail': v.score < 0.75,
    };
  }

  validationBarColor(): 'primary' | 'warn' {
    const v = this.validation();
    if (!v) return 'primary';
    return v.score >= 0.75 ? 'primary' : 'warn';
  }

  constructor(
    private readonly estimationService: EstimationService,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.estimationService.get(id).subscribe({
      next: e => { this.estimation.set(e); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
