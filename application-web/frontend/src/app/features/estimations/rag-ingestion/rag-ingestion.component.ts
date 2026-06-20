import { CommonModule } from '@angular/common';
import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  EstimationService,
  RagDocumentIngestResponse,
  SemanticSearchResponse,
} from '../estimation.service';

const SAMPLE_BUDGET = {
  budget_id: 'BUD-RAG-ADMIN-PORTAL-001',
  client_metadata: {
    name: 'B2B SaaS Customer Ops',
    sector: 'saas',
    country: 'ES',
  },
  project_summary: 'Admin portal for managing existing customer accounts with SSO, account search, plan management, usage metrics, audit logging, and role-based access control.',
  main_technology: 'react',
  year: 2026,
  total_estimated_hours: 520,
  components: [
    {
      component_id: 'AUTH-SSO',
      name: 'Authentication and SSO',
      description: 'Implement admin authentication with Google and Microsoft SSO, session handling, and secure backend integration.',
      tech_stack: ['React', 'FastAPI', 'OAuth2', 'PostgreSQL'],
      estimated_hours: 110,
      complexity: 'high',
      dependencies: [],
    },
    {
      component_id: 'CUSTOMER-LIST',
      name: 'Customer list and filtering',
      description: 'Build searchable and filterable customer account list optimized for admin workflows.',
      tech_stack: ['React', 'REST API', 'PostgreSQL'],
      estimated_hours: 90,
      complexity: 'medium',
      dependencies: ['AUTH-SSO'],
    },
    {
      component_id: 'CUSTOMER-DETAIL',
      name: 'Customer detail, plans, and usage',
      description: 'Show customer plan, usage metrics, and account details with responsive admin UI.',
      tech_stack: ['React', 'REST API'],
      estimated_hours: 95,
      complexity: 'medium',
      dependencies: ['CUSTOMER-LIST'],
    },
    {
      component_id: 'PLAN-CHANGES',
      name: 'Plan upgrade and downgrade workflow',
      description: 'Allow admins to upgrade or downgrade customer plans with validation and persistent audit trails.',
      tech_stack: ['React', 'FastAPI', 'PostgreSQL'],
      estimated_hours: 120,
      complexity: 'high',
      dependencies: ['CUSTOMER-DETAIL'],
    },
    {
      component_id: 'AUDIT-RBAC',
      name: 'Audit log and role-based access control',
      description: 'Record admin actions and enforce admin/read-only access rules across customer management screens.',
      tech_stack: ['FastAPI', 'PostgreSQL', 'React'],
      estimated_hours: 105,
      complexity: 'high',
      dependencies: ['AUTH-SSO', 'PLAN-CHANGES'],
    },
  ],
};

@Component({
  selector: 'app-rag-ingestion',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <div class="page-header">
      <div>
        <h1>RAG Ingestion</h1>
        <p>Ingest a budget-shaped document, persist its chunks and embeddings, then test semantic retrieval.</p>
      </div>
      <button mat-stroked-button type="button" (click)="loadSampleBudget()">
        <mat-icon>auto_fix_high</mat-icon>
        Use sample budget
      </button>
    </div>

    <section class="layout-grid">
      <mat-card class="panel">
        <mat-card-header>
          <mat-card-title>Ingest Document</mat-card-title>
        </mat-card-header>
        <mat-card-content class="form-grid">
          <mat-form-field appearance="outline">
            <mat-label>Source path</mat-label>
            <input matInput [(ngModel)]="sourcePath" />
          </mat-form-field>

          <mat-form-field appearance="outline">
            <mat-label>Document type</mat-label>
            <input matInput [(ngModel)]="documentType" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="json-field">
            <mat-label>Budget JSON content</mat-label>
            <textarea matInput rows="20" [(ngModel)]="contentJson" spellcheck="false"></textarea>
          </mat-form-field>
        </mat-card-content>
        <mat-card-actions align="end">
          <button mat-raised-button color="primary" type="button" (click)="ingest()" [disabled]="ingesting()">
            @if (ingesting()) {
              <mat-spinner diameter="18" />
            } @else {
              <mat-icon>upload_file</mat-icon>
            }
            Ingest
          </button>
        </mat-card-actions>
      </mat-card>

      <div class="side-stack">
        <mat-card class="panel">
          <mat-card-header>
            <mat-card-title>Ingestion Result</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            @if (ingestError()) {
              <div class="status error">{{ ingestError() }}</div>
            }
            @if (ingestResult()) {
              <div class="metric-grid">
                <div>
                  <span>Document ID</span>
                  <strong>{{ ingestResult()?.document_id }}</strong>
                </div>
                <div>
                  <span>Chunks</span>
                  <strong>{{ ingestResult()?.chunks_created }}</strong>
                </div>
                <div>
                  <span>Embedding dim</span>
                  <strong>{{ ingestResult()?.embedding_dimension }}</strong>
                </div>
                <div>
                  <span>Latency</span>
                  <strong>{{ ingestResult()?.ingestion_time_ms }} ms</strong>
                </div>
              </div>
            } @else if (!ingestError()) {
              <p class="empty-state">No document ingested yet.</p>
            }
          </mat-card-content>
        </mat-card>

        <mat-card class="panel">
          <mat-card-header>
            <mat-card-title>Retrieval Test</mat-card-title>
          </mat-card-header>
          <mat-card-content class="search-form">
            <mat-form-field appearance="outline">
              <mat-label>Query</mat-label>
              <textarea matInput rows="4" [(ngModel)]="query"></textarea>
            </mat-form-field>

            <mat-form-field appearance="outline" class="top-k-field">
              <mat-label>Top K</mat-label>
              <input matInput type="number" min="1" max="50" [(ngModel)]="topK" />
            </mat-form-field>
          </mat-card-content>
          <mat-card-actions align="end">
            <button mat-raised-button color="accent" type="button" (click)="search()" [disabled]="searching()">
              @if (searching()) {
                <mat-spinner diameter="18" />
              } @else {
                <mat-icon>search</mat-icon>
              }
              Search
            </button>
          </mat-card-actions>
        </mat-card>
      </div>
    </section>

    <mat-card class="panel results-panel">
      <mat-card-header>
        <mat-card-title>Retrieved Chunks</mat-card-title>
        @if (searchResult()) {
          <mat-card-subtitle>
            {{ searchResult()?.results?.length || 0 }} of {{ searchResult()?.k }} results in {{ searchResult()?.search_time_ms }} ms
          </mat-card-subtitle>
        }
      </mat-card-header>
      <mat-card-content>
        @if (searchError()) {
          <div class="status error">{{ searchError() }}</div>
        }
        @if (searchResult()?.results?.length) {
          <div class="chunk-list">
            @for (chunk of searchResult()?.results; track chunk.chunk_id) {
              <mat-expansion-panel>
                <mat-expansion-panel-header>
                  <mat-panel-title>Chunk {{ chunk.chunk_id }} · Document {{ chunk.document_id }}</mat-panel-title>
                  <mat-panel-description>{{ chunk.chunk_type }} · distance {{ chunk.distance.toFixed(4) }}</mat-panel-description>
                </mat-expansion-panel-header>

                <div class="chunk-body">
                  <div class="metadata-row">
                    @for (entry of metadataEntries(chunk.metadata); track entry.key) {
                      <span>{{ entry.key }}: {{ entry.value }}</span>
                    }
                  </div>
                  <p>{{ chunk.content }}</p>
                </div>
              </mat-expansion-panel>
            }
          </div>
        } @else if (searchResult()) {
          <p class="empty-state">No chunks matched this query.</p>
        } @else if (!searchError()) {
          <p class="empty-state">Run a search to inspect retrieved chunks.</p>
        }
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
    .page-header h1 { margin: 0 0 4px; font-size: 28px; }
    .page-header p { margin: 0; color: #5f6368; max-width: 760px; }
    .layout-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.8fr); gap: 16px; align-items: start; }
    .side-stack { display: grid; gap: 16px; }
    .panel { border-radius: 8px; }
    .form-grid, .search-form { display: grid; gap: 12px; }
    .json-field { width: 100%; }
    .top-k-field { max-width: 160px; }
    mat-card-actions button { display: inline-flex; align-items: center; gap: 8px; min-width: 118px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .metric-grid div { padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px; background: #fafafa; }
    .metric-grid span { display: block; font-size: 12px; color: #5f6368; margin-bottom: 4px; }
    .metric-grid strong { font-size: 20px; }
    .status { padding: 12px; border-radius: 8px; }
    .error { background: #ffebee; color: #b71c1c; }
    .empty-state { margin: 0; color: #6b7280; }
    .results-panel { margin-top: 16px; }
    .chunk-list { display: grid; gap: 10px; }
    .chunk-body { display: grid; gap: 12px; }
    .chunk-body p { margin: 0; white-space: pre-wrap; line-height: 1.5; }
    .metadata-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .metadata-row span { display: inline-flex; max-width: 100%; padding: 4px 8px; border-radius: 999px; background: #eef2ff; color: #283593; font-size: 12px; }
    @media (max-width: 900px) {
      .page-header, .layout-grid { display: block; }
      .page-header button, .side-stack { margin-top: 16px; }
    }
  `],
})
export class RagIngestionComponent {
  sourcePath = 'manual/admin-portal-budget.json';
  documentType = 'budget';
  contentJson = JSON.stringify(SAMPLE_BUDGET, null, 2);
  query = 'SSO admin portal audit log React PostgreSQL';
  topK = 5;

  ingesting = signal(false);
  searching = signal(false);
  ingestError = signal<string | null>(null);
  searchError = signal<string | null>(null);
  ingestResult = signal<RagDocumentIngestResponse | null>(null);
  searchResult = signal<SemanticSearchResponse | null>(null);
  canSearch = computed(() => this.query.trim().length > 0 && Number(this.topK) > 0);

  constructor(private readonly estimationService: EstimationService) {}

  loadSampleBudget(): void {
    this.sourcePath = `manual/admin-portal-budget-${Date.now()}.json`;
    this.documentType = 'budget';
    this.contentJson = JSON.stringify(SAMPLE_BUDGET, null, 2);
    this.query = 'SSO admin portal audit log React PostgreSQL';
    this.ingestError.set(null);
    this.searchError.set(null);
  }

  ingest(): void {
    this.ingestError.set(null);
    this.ingestResult.set(null);

    let parsedContent: Record<string, unknown>;
    try {
      parsedContent = JSON.parse(this.contentJson) as Record<string, unknown>;
    } catch {
      this.ingestError.set('The document content must be valid JSON.');
      return;
    }

    if (!this.sourcePath.trim() || !this.documentType.trim()) {
      this.ingestError.set('Source path and document type are required.');
      return;
    }

    this.ingesting.set(true);
    this.estimationService.ingestRagDocument({
      source_path: this.sourcePath.trim(),
      document_type: this.documentType.trim(),
      content: parsedContent,
    }).subscribe({
      next: result => {
        this.ingestResult.set(result);
        this.ingesting.set(false);
      },
      error: err => {
        this.ingestError.set(this.formatError(err, 'Failed to ingest document.'));
        this.ingesting.set(false);
      },
    });
  }

  search(): void {
    this.searchError.set(null);
    this.searchResult.set(null);

    if (!this.canSearch()) {
      this.searchError.set('Query and Top K are required.');
      return;
    }

    this.searching.set(true);
    this.estimationService.searchSemantic({
      query: this.query.trim(),
      k: Math.max(1, Math.min(50, Number(this.topK) || 5)),
    }).subscribe({
      next: result => {
        this.searchResult.set(result);
        this.searching.set(false);
      },
      error: err => {
        this.searchError.set(this.formatError(err, 'Failed to search chunks.'));
        this.searching.set(false);
      },
    });
  }

  metadataEntries(metadata: Record<string, unknown>) {
    return Object.entries(metadata ?? {}).map(([key, value]) => ({ key, value }));
  }

  private formatError(err: unknown, fallback: string): string {
    const candidate = err as { error?: { detail?: unknown }; message?: string };
    const detail = candidate?.error?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map(item => item?.msg ?? JSON.stringify(item)).join(', ');
    }
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
    return candidate?.message ?? fallback;
  }
}
