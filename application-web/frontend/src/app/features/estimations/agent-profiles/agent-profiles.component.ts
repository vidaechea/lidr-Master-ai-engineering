import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSelectModule } from '@angular/material/select';

import {
  AgentProfile,
  AgentProfileConfig,
  RagEstimationService,
} from '../rag-estimation.service';

@Component({
  selector: 'app-agent-profiles',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
    MatCheckboxModule,
    MatSelectModule,
  ],
  template: `
    <div class="page-header">
      <h1>Agent Profiles</h1>
      <button mat-raised-button color="primary" (click)="startNew()">
        <mat-icon>add</mat-icon> New profile
      </button>
    </div>

    @if (error()) {
      <mat-card class="error-card">{{ error() }}</mat-card>
    }

    @if (editing()) {
      <mat-card class="editor-card">
        <mat-card-title>{{ editId() ? 'Edit profile' : 'New profile' }}</mat-card-title>
        <mat-card-content>
          <div class="grid">
            <mat-form-field appearance="outline">
              <mat-label>Name</mat-label>
              <input matInput [(ngModel)]="draftName" />
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Model</mat-label>
              <input matInput [(ngModel)]="draftModel" />
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Reasoning effort</mat-label>
              <mat-select [(ngModel)]="draftEffort">
                <mat-option [value]="null">Default</mat-option>
                <mat-option value="minimal">minimal</mat-option>
                <mat-option value="low">low</mat-option>
                <mat-option value="medium">medium</mat-option>
                <mat-option value="high">high</mat-option>
              </mat-select>
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Max iterations</mat-label>
              <input matInput type="number" min="1" max="20" [(ngModel)]="draftMaxIterations" />
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Search top_k</mat-label>
              <input matInput type="number" min="1" max="30" [(ngModel)]="draftTopK" />
            </mat-form-field>

            <mat-form-field appearance="outline">
              <mat-label>Distance threshold</mat-label>
              <input matInput type="number" min="0" max="2" step="0.05" [(ngModel)]="draftDistance" />
            </mat-form-field>
          </div>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Persona</mat-label>
            <textarea matInput rows="3" [(ngModel)]="draftPersona"></textarea>
          </mat-form-field>

          <mat-checkbox [(ngModel)]="draftDefault">Default profile</mat-checkbox>
        </mat-card-content>

        <mat-card-actions>
          <button mat-raised-button color="primary" (click)="save()">Save</button>
          <button mat-button (click)="cancel()">Cancel</button>
        </mat-card-actions>
      </mat-card>
    }

    <div class="cards">
      @for (profile of profiles(); track profile.id) {
        <mat-card>
          <mat-card-title>
            {{ profile.name }}
            @if (profile.is_default) {
              <span class="default-pill">default</span>
            }
          </mat-card-title>
          <mat-card-content>
            <p class="muted">{{ profile.persona || 'No persona' }}</p>
            <p>model: {{ profile.config.model || 'service default' }}</p>
            <p>effort: {{ profile.config.reasoning_effort || 'service default' }}</p>
          </mat-card-content>
          <mat-card-actions>
            <button mat-button (click)="edit(profile)">Edit</button>
            <button mat-button color="warn" (click)="remove(profile)">Delete</button>
          </mat-card-actions>
        </mat-card>
      }
    </div>
  `,
  styles: [
    `
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:12px; }
    .editor-card { margin-bottom:16px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin-top:12px; }
    .full-width { width:100%; }
    .default-pill { margin-left:8px; font-size:12px; text-transform:uppercase; color:#1976d2; }
    .muted { color:#666; }
    .error-card { margin-bottom:12px; color:#c62828; }
  `,
  ],
})
export class AgentProfilesComponent implements OnInit {
  readonly profiles = signal<AgentProfile[]>([]);
  readonly error = signal<string | null>(null);
  readonly editing = signal(false);
  readonly editId = signal<string | null>(null);

  draftName = '';
  draftPersona = '';
  draftModel: string | null = null;
  draftEffort: AgentProfileConfig['reasoning_effort'] | null = null;
  draftMaxIterations: number | null = null;
  draftTopK: number | null = null;
  draftDistance: number | null = null;
  draftDefault = false;

  constructor(private readonly ragService: RagEstimationService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.ragService.listAgentProfiles().subscribe({
      next: profiles => this.profiles.set(profiles),
      error: err => this.error.set(err?.error?.detail || 'Failed to load profiles'),
    });
  }

  startNew(): void {
    this.editId.set(null);
    this.resetDraft();
    this.editing.set(true);
  }

  edit(profile: AgentProfile): void {
    this.editId.set(profile.id);
    this.draftName = profile.name;
    this.draftPersona = profile.persona || '';
    this.draftModel = profile.config.model || null;
    this.draftEffort = profile.config.reasoning_effort || null;
    this.draftMaxIterations = profile.config.max_iterations || null;
    this.draftTopK = profile.config.search_top_k || null;
    this.draftDistance = profile.config.search_distance_threshold || null;
    this.draftDefault = profile.is_default;
    this.editing.set(true);
  }

  save(): void {
    this.error.set(null);
    const body = {
      name: this.draftName.trim(),
      persona: this.draftPersona?.trim() || null,
      is_default: this.draftDefault,
      config: {
        model: this.draftModel || null,
        reasoning_effort: this.draftEffort || null,
        max_iterations: this.draftMaxIterations,
        search_top_k: this.draftTopK,
        search_distance_threshold: this.draftDistance,
      },
    };

    if (!body.name) {
      this.error.set('Name is required');
      return;
    }

    const id = this.editId();
    const req$ = id
      ? this.ragService.updateAgentProfile(id, body)
      : this.ragService.createAgentProfile(body);

    req$.subscribe({
      next: () => {
        this.editing.set(false);
        this.load();
      },
      error: err => this.error.set(err?.error?.detail || 'Failed to save profile'),
    });
  }

  remove(profile: AgentProfile): void {
    this.error.set(null);
    this.ragService.deleteAgentProfile(profile.id).subscribe({
      next: () => this.load(),
      error: err => this.error.set(err?.error?.detail || 'Failed to delete profile'),
    });
  }

  cancel(): void {
    this.editing.set(false);
  }

  private resetDraft(): void {
    this.draftName = '';
    this.draftPersona = '';
    this.draftModel = null;
    this.draftEffort = null;
    this.draftMaxIterations = null;
    this.draftTopK = null;
    this.draftDistance = null;
    this.draftDefault = false;
  }
}
