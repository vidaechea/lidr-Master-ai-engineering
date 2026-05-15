import { Component, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSliderModule } from '@angular/material/slider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { EstimationCreate, EstimationService, GuardrailError, GuardrailReason } from '../estimation.service';

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
    MatCardModule, MatFormFieldModule, MatIconModule, MatInputModule, MatSelectModule,
    MatButtonModule, MatCheckboxModule, MatSliderModule, MatProgressSpinnerModule,
  ],
  template: `
    <mat-card class="form-card">
      <mat-card-header>
        <mat-card-title>New Estimation</mat-card-title>
        <mat-card-subtitle>Paste a meeting transcript or project description</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <form (ngSubmit)="submit()" #f="ngForm">

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Transcript / Description</mat-label>
            <textarea matInput name="transcription" [(ngModel)]="form.transcription"
              rows="8" required minlength="20"
              placeholder="Paste your meeting notes or project description hereâ€¦"></textarea>
          </mat-form-field>

          <div class="params-row">
            <mat-form-field appearance="outline">
              <mat-label>Model</mat-label>
              <mat-select name="model" [(ngModel)]="form.model">
                <mat-option value="">Default</mat-option>
                <mat-option value="gpt-4o-mini">GPT-4o mini</mat-option>
                <mat-option value="gpt-5.4-mini">GPT-5.4 mini</mat-option>
                <mat-option value="claude-sonnet-4-6">Claude Sonnet 4.6</mat-option>
                <mat-option value="claude-haiku-4-5-20251001">Claude Haiku 4.5</mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Output format</mat-label>
              <mat-select name="outputFormat" [(ngModel)]="form.output_format">
                <mat-option value="phases_table">Phases table</mat-option>
                <mat-option value="line_items">Line items</mat-option>
                <mat-option value="narrative">Narrative</mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Prompt version</mat-label>
              <mat-select name="promptVersion" [(ngModel)]="form.prompt_version">
                <mat-option value="v1">v1</mat-option>
                <mat-option value="v2">v2</mat-option>
              </mat-select>
            </mat-form-field>
          </div>

          <mat-checkbox name="preCal" [(ngModel)]="form.pre_call">
            Extract requirements before estimating (pre_call)
          </mat-checkbox>

          @if (guardrailError()) {
            <div class="guardrail-warning" [attr.data-reason]="guardrailError()!.reason">
              <mat-icon>{{ guardrailIcon(guardrailError()!.reason) }}</mat-icon>
              <span>{{ guardrailError()!.message }}</span>
            </div>
          }

          @if (error()) {
            <p class="error-msg">{{ error() }}</p>
          }

          <div class="actions">
            <button mat-raised-button color="primary" type="submit" [disabled]="loading()">
              @if (loading()) {
                <mat-spinner diameter="20"></mat-spinner>
              } @else {
                Run Estimation
              }
            </button>
          </div>
        </form>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .form-card { max-width:900px; margin:24px auto; padding:16px; }
    .full-width { width:100%; margin-bottom:16px; }
    .params-row { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; }
    .params-row mat-form-field { flex:1; min-width:160px; }
    .actions { display:flex; justify-content:flex-end; margin-top:16px; }
    .error-msg { color:var(--mat-sys-error); }
    .guardrail-warning {
      display:flex; align-items:center; gap:8px;
      padding:12px 16px; margin:12px 0;
      border-radius:4px;
      background:color-mix(in srgb, var(--mat-sys-error) 10%, transparent);
      color:var(--mat-sys-error);
      border-left:4px solid var(--mat-sys-error);
    }
    .guardrail-warning mat-icon { flex-shrink:0; }
  `],
})
export class EstimationFormComponent {
  form: EstimationCreate = {
    transcription: '',
    output_format: 'phases_table',
    prompt_version: 'v1',
    pre_call: false,
    num_examples: 3,
    max_output_tokens: 2048,
  };
  loading = signal(false);
  error = signal<string | null>(null);
  guardrailError = signal<GuardrailError | null>(null);

  constructor(
    private estimationService: EstimationService,
    private router: Router,
    private route: ActivatedRoute,
  ) {
    // Pre-fill projectId from query params if coming from project detail.
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
    this.estimationService.create(this.form).subscribe({
      next: result => this.router.navigate(['/estimations', result.id]),
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        if (detail?.reason && (err.status === 400 || err.status === 422)) {
          this.guardrailError.set(detail as GuardrailError);
        } else {
          const msg = typeof detail === 'string' ? detail : (detail?.message ?? err.message ?? 'Unknown error');
          this.error.set(`Estimation failed (${err.status}): ${msg}`);
        }
        this.loading.set(false);
      },
    });
  }
}
