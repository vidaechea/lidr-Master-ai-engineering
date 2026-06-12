import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';

import { EstimationService, RuntimeModelsResponse } from '../estimation.service';

type PendingChanges = Record<string, string | null>;

@Component({
  selector: 'app-model-settings',
  standalone: true,
  imports: [FormsModule, MatButtonModule, MatCardModule],
  template: `
    <div class="page-header">
      <h1>AI Model Settings</h1>
      <button mat-raised-button color="primary" type="button" (click)="save()" [disabled]="saving()">
        Save
      </button>
    </div>

    @if (loading()) {
      <p>Loading model configuration...</p>
    } @else if (error()) {
      <mat-card class="error-card">
        <mat-card-content>{{ error() }}</mat-card-content>
      </mat-card>
    } @else {
      <div class="settings-grid">
        @for (entry of modelEntries(); track entry.key) {
          <mat-card class="setting-card">
            <mat-card-header>
              <mat-card-title>{{ entry.key }}</mat-card-title>
            </mat-card-header>
            <mat-card-content>
              <p class="meta-line">
                Effective: <strong>{{ entry.value.effective }}</strong>
                | Default: {{ entry.value.default }}
                | Overridden: {{ entry.value.overridden ? 'Yes' : 'No' }}
              </p>

              <label [for]="entry.key" class="select-label">Model override</label>
              <select
                class="model-select"
                [id]="entry.key"
                [ngModel]="selected(entry.key, entry.value)"
                (ngModelChange)="onSelect(entry.key, entry.value.default, $event)">
                <option value="">Use default</option>
                @for (model of availableModels(); track model) {
                  <option [value]="model">{{ model }}</option>
                }
              </select>
            </mat-card-content>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
    .settings-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(360px,1fr)); gap:16px; }
    .setting-card { height: 100%; }
    .meta-line { margin: 0 0 12px; font-size: 13px; }
    .select-label { display: block; margin-bottom: 6px; font-size: 13px; }
    .model-select {
      width: 100%;
      min-height: 36px;
      border-radius: 6px;
      border: 1px solid #bbb;
      padding: 6px 8px;
      font-size: 14px;
      background: #fff;
    }
    .error-card { border-left: 4px solid #c62828; }
  `],
})
export class ModelSettingsComponent implements OnInit {
  loading = signal(true);
  saving = signal(false);
  error = signal<string | null>(null);
  runtime = signal<RuntimeModelsResponse | null>(null);
  pending = signal<PendingChanges>({});

  constructor(private readonly estimationService: EstimationService) {}

  ngOnInit(): void {
    this.reload();
  }

  availableModels() {
    return this.runtime()?.available_models ?? [];
  }

  modelEntries() {
    const models = this.runtime()?.models ?? {};
    return Object.entries(models).map(([key, value]) => ({ key, value }));
  }

  selected(key: string, value: { effective: string; default: string; overridden: boolean }): string {
    const pending = this.pending()[key];
    if (pending === null) {
      return '';
    }
    if (typeof pending === 'string') {
      return pending;
    }
    return value.overridden ? value.effective : '';
  }

  onSelect(key: string, defaultValue: string, selectedValue: string) {
    const trimmed = selectedValue?.trim() ?? '';
    this.pending.update(curr => {
      const next = { ...curr };
      if (!trimmed || trimmed === defaultValue) {
        next[key] = null;
      } else {
        next[key] = trimmed;
      }
      return next;
    });
  }

  save() {
    const changes = this.pending();
    if (Object.keys(changes).length === 0) {
      return;
    }

    this.saving.set(true);
    this.error.set(null);
    this.estimationService.updateRuntimeModels(changes).subscribe({
      next: payload => {
        this.runtime.set(payload);
        this.pending.set({});
        this.saving.set(false);
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to save model settings';
        this.error.set(String(detail));
        this.saving.set(false);
      },
    });
  }

  private reload() {
    this.loading.set(true);
    this.error.set(null);
    this.estimationService.getRuntimeModels().subscribe({
      next: payload => {
        this.runtime.set(payload);
        this.loading.set(false);
      },
      error: err => {
        const detail = err?.error?.detail ?? 'Failed to load model settings';
        this.error.set(String(detail));
        this.loading.set(false);
      },
    });
  }
}
