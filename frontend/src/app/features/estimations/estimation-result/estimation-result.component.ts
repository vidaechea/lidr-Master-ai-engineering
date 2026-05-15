import { Component, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DatePipe, DecimalPipe } from '@angular/common';
import { EstimationOut, EstimationService } from '../estimation.service';

@Component({
  selector: 'app-estimation-result',
  standalone: true,
  imports: [
    RouterLink,
    MatCardModule, MatButtonModule, MatChipsModule, MatDividerModule,
    MatProgressSpinnerModule, DatePipe, DecimalPipe,
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
  `],
})
export class EstimationResultComponent implements OnInit {
  estimation = signal<EstimationOut | null>(null);
  loading = signal(true);
  statusColor = () => this.estimation()?.status === 'completed' ? 'primary' : 'warn';

  constructor(
    private estimationService: EstimationService,
    private route: ActivatedRoute,
  ) {}

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.estimationService.get(id).subscribe({
      next: e => { this.estimation.set(e); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
