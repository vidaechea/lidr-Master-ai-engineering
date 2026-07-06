import { Component, OnDestroy, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';

import {
  RagCollectionStats,
  RagEstimationService,
  RagIndexJob,
} from '../rag-estimation.service';

@Component({
  selector: 'app-rag-index',
  standalone: true,
  imports: [FormsModule, MatButtonModule, MatCardModule],
  template: `
    <div class="page-header">
      <h1>RAG Index</h1>
      <button mat-stroked-button type="button" (click)="refreshIndexStats()" [disabled]="indexLoading()">
        Refresh stats
      </button>
    </div>

    <mat-card class="form-card">
      <mat-card-content>
        <div class="index-actions">
          <label class="field-label">Sample documents to enqueue</label>
          <input class="topk-input" type="number" min="1" max="20" [(ngModel)]="sampleDocsCount" />
          <button mat-raised-button color="accent" type="button" (click)="startSampleIndexRun()" [disabled]="indexLoading()">
            Start sample index run
          </button>
        </div>

        @if (indexError()) {
          <p class="index-error">{{ indexError() }}</p>
        }

        @if (indexJob()) {
          <div class="index-job-panel">
            <p><strong>Job</strong> {{ indexJob()!.job_id }}</p>
            <p><strong>Status</strong> {{ indexJob()!.status }}</p>
            <p><strong>Documents processed</strong> {{ indexJob()!.documents_processed }}</p>
            @if (indexJob()!.error_message) {
              <p><strong>Error</strong> {{ indexJob()!.error_message }}</p>
            }
          </div>
        }
      </mat-card-content>
    </mat-card>

    @if (indexCollections().length > 0) {
      <div class="results-grid compact-grid">
        @for (collection of indexCollections(); track collection.collection) {
          <mat-card class="result-card">
            <mat-card-header>
              <mat-card-title>{{ collection.collection }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <p>Documents: <strong>{{ collection.documents }}</strong></p>
              <p>Chunks: <strong>{{ collection.chunks }}</strong></p>
              <p>HNSW indexed: <strong>{{ collection.hnsw_indexed ? 'yes' : 'no' }}</strong></p>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
    .form-card { margin-bottom: 16px; }
    .index-actions { display:flex; gap:12px; align-items:end; flex-wrap:wrap; }
    .index-job-panel { margin-top: 12px; padding: 10px; border-radius: 8px; background: #f5f5f5; }
    .index-error { color: #c62828; margin-top: 10px; }
    .field-label { display:block; margin: 12px 0 6px; font-size: 13px; }
    .topk-input { width:120px; min-height:36px; padding:6px 8px; }
    .results-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:16px; margin-top:16px; }
    .compact-grid { grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); }
    .result-card { height:100%; }
  `],
})
export class RagIndexComponent implements OnDestroy {
  indexLoading = signal(false);
  indexError = signal<string | null>(null);
  indexJob = signal<RagIndexJob | null>(null);
  indexCollections = signal<RagCollectionStats[]>([]);
  sampleDocsCount = 2;
  private pollTimer: number | null = null;

  constructor(private readonly ragEstimationService: RagEstimationService) {
    this.refreshIndexStats();
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  refreshIndexStats() {
    this.indexLoading.set(true);
    this.indexError.set(null);
    this.ragEstimationService.getIndexStats().subscribe({
      next: payload => {
        this.indexCollections.set(payload.collections);
        this.indexLoading.set(false);
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to load corpus index stats';
        this.indexError.set(String(detail));
        this.indexLoading.set(false);
      },
    });
  }

  startSampleIndexRun() {
    this.indexLoading.set(true);
    this.indexError.set(null);
    this.stopPolling();

    const requested = Number(this.sampleDocsCount) || 1;
    const bounded = Math.max(1, Math.min(20, requested));
    const documents = this.buildSampleBudgets(bounded);

    this.ragEstimationService.createIndexRun({
      documents,
      document_type: 'historical_budget',
      chunk_type: 'budget_component',
    }).subscribe({
      next: payload => {
        this.pollJob(payload.job_id);
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to start corpus index run';
        this.indexError.set(String(detail));
        this.indexLoading.set(false);
      },
    });
  }

  private pollJob(jobId: string) {
    this.ragEstimationService.getIndexJob(jobId).subscribe({
      next: job => {
        this.indexJob.set(job);
        if (job.status === 'pending' || job.status === 'running') {
          this.pollTimer = globalThis.setTimeout(() => this.pollJob(jobId), 1500);
          return;
        }
        this.indexLoading.set(false);
        this.refreshIndexStats();
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to poll index job';
        this.indexError.set(String(detail));
        this.indexLoading.set(false);
      },
    });
  }

  private stopPolling() {
    if (this.pollTimer !== null) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private buildSampleBudgets(count: number): Record<string, unknown>[] {
    const docs: Record<string, unknown>[] = [];
    for (let index = 0; index < count; index += 1) {
      docs.push({
        budget_id: `S11-DEMO-${Date.now()}-${index + 1}`,
        client_metadata: {
          name: 'Session 11 Demo Client',
          sector: 'saas',
          country: 'ES',
        },
        project_summary: `Demo portal scope ${index + 1}`,
        main_technology: 'python',
        year: 2024,
        total_estimated_hours: 40,
        components: [
          {
            component_id: `DISC-${index + 1}`,
            name: 'Discovery',
            description: 'Requirements discovery and planning.',
            tech_stack: ['python', 'fastapi'],
            estimated_hours: 40,
            complexity: 'medium',
            dependencies: [],
          },
        ],
      });
    }
    return docs;
  }
}
