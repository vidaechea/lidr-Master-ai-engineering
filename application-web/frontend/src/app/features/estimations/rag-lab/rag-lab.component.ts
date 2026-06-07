import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';

import {
  ChunkingComparisonResponse,
  EstimationService,
} from '../estimation.service';

type StrategyName = 'structural' | 'fixed_size';

@Component({
  selector: 'app-rag-lab',
  standalone: true,
  imports: [FormsModule, MatButtonModule, MatCardModule],
  template: `
    <div class="page-header">
      <h1>RAG Lab</h1>
      <button mat-raised-button color="primary" type="button" (click)="run()" [disabled]="loading()">
        Run comparison
      </button>
    </div>

    <mat-card class="form-card">
      <mat-card-content>
        <label class="field-label">Queries (one per line)</label>
        <textarea class="queries-input" [(ngModel)]="queriesText"></textarea>

        <label class="field-label">Top K</label>
        <input class="topk-input" type="number" min="1" max="10" [(ngModel)]="topK" />

        <div class="strategy-grid">
          @for (strategy of strategies; track strategy) {
            <label class="checkbox-row">
              <input
                type="checkbox"
                [checked]="selectedStrategies().includes(strategy)"
                (change)="toggleStrategy(strategy, $any($event.target).checked)" />
              <span>{{ strategy }}</span>
            </label>
          }
        </div>
      </mat-card-content>
    </mat-card>

    @if (error()) {
      <mat-card class="error-card">
        <mat-card-content>{{ error() }}</mat-card-content>
      </mat-card>
    }

    @if (result()) {
      <div class="results-grid">
        @for (entry of statsEntries(); track entry.key) {
          <mat-card class="result-card">
            <mat-card-header>
              <mat-card-title>{{ entry.key }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <p>Chunks: <strong>{{ entry.value.total_chunks }}</strong></p>
              <p>Tokens: <strong>{{ entry.value.total_tokens }}</strong></p>
              <p>Avg/chunk: <strong>{{ entry.value.avg_tokens_per_chunk.toFixed(1) }}</strong></p>
              <p>Estimated cost: <strong>{{ entry.value.estimated_cost_usd }}</strong></p>
            </mat-card-content>
          </mat-card>
        }
      </div>

      <div class="queries-results">
        @for (entry of queryEntries(); track entry.key) {
          <mat-card class="result-card">
            <mat-card-header>
              <mat-card-title>{{ entry.key }} queries</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              @for (query of entry.value; track query.query) {
                <div class="query-block">
                  <p><strong>{{ query.query }}</strong></p>
                  @for (hit of query.results; track hit.chunk_id) {
                    <p class="hit-row">
                      {{ hit.chunk_id }} · sim={{ hit.similarity.toFixed(3) }}
                    </p>
                  }
                </div>
              }
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
    .form-card { margin-bottom: 16px; }
    .field-label { display:block; margin: 12px 0 6px; font-size: 13px; }
    .queries-input { width:100%; min-height:120px; padding:8px; box-sizing:border-box; }
    .topk-input { width:120px; min-height:36px; padding:6px 8px; }
    .strategy-grid { display:flex; gap:16px; margin-top:16px; flex-wrap:wrap; }
    .checkbox-row { display:flex; gap:8px; align-items:center; }
    .results-grid, .queries-results { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:16px; margin-top:16px; }
    .result-card { height:100%; }
    .query-block { margin-bottom: 16px; }
    .hit-row { font-size: 13px; margin: 4px 0; }
    .error-card { border-left:4px solid #c62828; margin-bottom: 16px; }
  `],
})
export class RagLabComponent {
  strategies: StrategyName[] = ['structural', 'fixed_size'];
  selectedStrategies = signal<StrategyName[]>(['structural', 'fixed_size']);
  loading = signal(false);
  error = signal<string | null>(null);
  result = signal<ChunkingComparisonResponse | null>(null);
  queriesText = 'oauth backend';
  topK = 3;

  constructor(private readonly estimationService: EstimationService) {}

  statsEntries() {
    return Object.entries(this.result()?.stats_per_strategy ?? {}).map(([key, value]) => ({ key, value }));
  }

  queryEntries() {
    return Object.entries(this.result()?.queries_per_strategy ?? {}).map(([key, value]) => ({ key, value }));
  }

  toggleStrategy(strategy: StrategyName, checked: boolean) {
    this.selectedStrategies.update(current => {
      if (checked) {
        return current.includes(strategy) ? current : [...current, strategy];
      }
      return current.filter(item => item !== strategy);
    });
  }

  run() {
    this.loading.set(true);
    this.error.set(null);
    this.estimationService.compareChunking({
      queries: this.queriesText.split('\n').map(item => item.trim()).filter(Boolean),
      strategies: this.selectedStrategies(),
      top_k: Math.max(1, Math.min(10, Number(this.topK) || 3)),
    }).subscribe({
      next: payload => {
        this.result.set(payload);
        this.loading.set(false);
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to run chunking comparison';
        this.error.set(String(detail));
        this.loading.set(false);
      },
    });
  }
}