import { Component, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { Router } from '@angular/router';
import {
  GraphProgress,
  GraphRunState,
  RagEstimationService,
} from '../rag-estimation.service';

interface EditableTask {
  name: string;
  description?: string;
  estimated_hours?: number | null;
}

interface EditableModule {
  name: string;
  tasks: EditableTask[];
}

@Component({
  selector: 'app-graph-run',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatInputModule,
    MatFormFieldModule,
  ],
  template: `
    <div class="page">
      <div class="header">
        <h1>Ejecución del proceso agentico</h1>
        <button mat-stroked-button color="primary" (click)="goToFlow()">Ver flujo</button>
      </div>

      <mat-card class="start-card">
        <mat-card-header>
          <mat-card-title>1) Iniciar run</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <mat-form-field appearance="outline" class="full">
            <mat-label>Transcripción</mat-label>
            <textarea
              matInput
              rows="7"
              [(ngModel)]="transcript"
              placeholder="Pega la transcripción del discovery call"
            ></textarea>
          </mat-form-field>
          <div class="actions">
            <button mat-raised-button color="primary" (click)="start()" [disabled]="loading()">
              Iniciar proceso
            </button>
            @if (runId()) {
              <button mat-button color="primary" (click)="refreshState()">Refrescar estado</button>
            }
          </div>
          @if (error()) {
            <p class="error">{{ error() }}</p>
          }
        </mat-card-content>
      </mat-card>

      @if (state()) {
        <mat-card class="status-card">
          <mat-card-content>
            <p><strong>Run:</strong> {{ state()!.estimation_id }}</p>
            <p><strong>Estado:</strong> {{ state()!.state }}</p>
            <p><strong>Complejidad:</strong> {{ state()!.complexity || 'n/a' }}</p>
            @if (state()!.status) {
              <p><strong>Status final:</strong> {{ state()!.status }}</p>
            }
          </mat-card-content>
        </mat-card>
      }

      @if (activity().length > 0) {
        <mat-card class="feed-card">
          <mat-card-header>
            <mat-card-title>Actividad en vivo</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <ul class="feed">
              @for (item of activity(); track item.seq) {
                <li>
                  <span class="seq">#{{ item.seq }}</span>
                  <span class="label">{{ item.label }}</span>
                  <span class="msg">{{ item.message }}</span>
                </li>
              }
            </ul>
          </mat-card-content>
        </mat-card>
      }

      @if (state()?.pending_gate?.gate === 'structure_review') {
        <mat-card class="gate-card">
          <mat-card-header>
            <mat-card-title>2) Gate 1: revisión de estructura</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            @for (module of structureModules(); track $index; let mi = $index) {
              <div class="module-box">
                <mat-form-field appearance="outline" class="full">
                  <mat-label>Módulo</mat-label>
                  <input matInput [(ngModel)]="module.name" />
                </mat-form-field>

                @for (task of module.tasks; track $index; let ti = $index) {
                  <div class="task-row">
                    <mat-form-field appearance="outline" class="task-name">
                      <mat-label>Tarea</mat-label>
                      <input matInput [(ngModel)]="task.name" />
                    </mat-form-field>
                    <mat-form-field appearance="outline" class="task-desc">
                      <mat-label>Descripción</mat-label>
                      <input matInput [(ngModel)]="task.description" />
                    </mat-form-field>
                  </div>
                }
              </div>
            }
            <button mat-raised-button color="primary" (click)="resumeStructure()" [disabled]="loading()">
              Aprobar estructura y continuar
            </button>
          </mat-card-content>
        </mat-card>
      }

      @if (state()?.pending_gate?.gate === 'final_review') {
        <mat-card class="gate-card">
          <mat-card-header>
            <mat-card-title>3) Gate 2: validación final</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            @for (module of finalModules(); track $index) {
              <div class="module-box">
                <h4>{{ module.name }}</h4>
                @for (task of module.tasks; track $index) {
                  <div class="task-hours-row">
                    <span>{{ task.name }}</span>
                    <mat-form-field appearance="outline" class="hours-input">
                      <mat-label>Horas</mat-label>
                      <input matInput type="number" min="0" step="0.5" [(ngModel)]="task.estimated_hours" />
                    </mat-form-field>
                  </div>
                }
              </div>
            }

            <div class="actions-row">
              <label>
                <input type="checkbox" [(ngModel)]="wantProposal" /> Generar propuesta comercial
              </label>
              <button mat-raised-button color="primary" (click)="resumeFinal()" [disabled]="loading()">
                Validar y finalizar
              </button>
            </div>
          </mat-card-content>
        </mat-card>
      }

      @if (state()?.state === 'completed') {
        <mat-card class="result-card">
          <mat-card-header>
            <mat-card-title>4) Resultado final</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <pre>{{ toPrettyJson(state()?.estimate) }}</pre>
            @if (state()?.proposal) {
              <h3>Propuesta</h3>
              <pre>{{ state()?.proposal }}</pre>
            } @else {
              <button mat-stroked-button color="primary" (click)="generateProposal()">
                Generar propuesta ahora
              </button>
            }
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: [
    `
      .page { max-width: 1080px; margin: 0 auto; padding: 24px; }
      .header { display:flex; align-items:center; justify-content:space-between; margin-bottom: 16px; }
      .full { width: 100%; }
      .start-card, .status-card, .feed-card, .gate-card, .result-card { margin-bottom: 14px; }
      .actions { display:flex; gap:10px; align-items:center; }
      .error { color: #c62828; margin-top: 10px; }
      .feed { list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:6px; }
      .feed li { display:flex; gap:8px; font-size: 13px; }
      .seq { color:#667085; min-width: 42px; }
      .label { font-weight:600; min-width: 95px; }
      .module-box { border: 1px solid #d8dee8; border-radius: 10px; padding: 10px; margin-bottom: 10px; }
      .task-row { display:flex; gap:8px; }
      .task-name { width: 32%; }
      .task-desc { width: 68%; }
      .task-hours-row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
      .hours-input { width: 130px; }
      .actions-row { display:flex; justify-content:space-between; align-items:center; margin-top: 10px; }
      pre { white-space: pre-wrap; background: #f6f8fa; padding: 12px; border-radius: 8px; overflow: auto; }
      @media (max-width: 900px) {
        .task-row { flex-direction: column; }
        .task-name, .task-desc { width: 100%; }
        .actions-row { flex-direction: column; align-items:flex-start; gap:10px; }
      }
    `,
  ],
})
export class GraphRunComponent implements OnDestroy {
  transcript = '';
  wantProposal = true;

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly runId = signal<string | null>(null);
  readonly state = signal<GraphRunState | null>(null);
  readonly activity = signal<GraphProgress['activity']>([]);
  readonly structureModules = signal<EditableModule[]>([]);
  readonly finalModules = signal<EditableModule[]>([]);

  private pollHandle: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly ragService: RagEstimationService,
    private readonly router: Router,
  ) {}

  ngOnDestroy(): void {
    this.stopPolling();
  }

  goToFlow(): void {
    this.router.navigate(['/estimations/graph-flow']);
  }

  start(): void {
    if (!this.transcript.trim() || this.transcript.trim().length < 20) {
      this.error.set('La transcripción debe tener al menos 20 caracteres.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);

    this.ragService.startGraphStream({ transcript: this.transcript.trim() }).subscribe({
      next: progress => {
        this.runId.set(progress.estimation_id);
        this.state.set(progress);
        this.activity.set(progress.activity || []);
        this.loading.set(false);
        this.startPolling();
      },
      error: err => {
        this.error.set(err?.error?.detail || 'No se pudo iniciar el flujo graph.');
        this.loading.set(false);
      },
    });
  }

  refreshState(): void {
    const estimationId = this.runId();
    if (!estimationId) return;

    this.loading.set(true);
    this.ragService.getGraphState(estimationId).subscribe({
      next: state => {
        this.state.set(state);
        this.loading.set(false);
        this.syncEditableViews(state);
      },
      error: err => {
        this.error.set(err?.error?.detail || 'No se pudo recuperar el estado del run.');
        this.loading.set(false);
      },
    });
  }

  resumeStructure(): void {
    const estimationId = this.runId();
    if (!estimationId) return;

    this.loading.set(true);
    this.ragService.resumeGraphStream(estimationId, {
      decision: {
        approved: true,
        modules: this.structureModules(),
      },
    }).subscribe({
      next: progress => {
        this.state.set(progress);
        this.activity.set(progress.activity || this.activity());
        this.loading.set(false);
        this.startPolling();
      },
      error: err => {
        this.error.set(err?.error?.detail || 'No se pudo reanudar gate 1.');
        this.loading.set(false);
      },
    });
  }

  resumeFinal(): void {
    const estimationId = this.runId();
    if (!estimationId) return;

    this.loading.set(true);
    this.ragService.resumeGraphStream(estimationId, {
      decision: {
        validated: true,
        want_proposal: this.wantProposal,
        estimate_overrides: { modules: this.finalModules() },
      },
    }).subscribe({
      next: progress => {
        this.state.set(progress);
        this.activity.set(progress.activity || this.activity());
        this.loading.set(false);
        this.startPolling();
      },
      error: err => {
        this.error.set(err?.error?.detail || 'No se pudo reanudar gate 2.');
        this.loading.set(false);
      },
    });
  }

  generateProposal(): void {
    const estimationId = this.runId();
    if (!estimationId) return;

    this.loading.set(true);
    this.ragService.generateGraphProposal(estimationId).subscribe({
      next: proposal => {
        const current = this.state();
        if (current) {
          this.state.set({ ...current, proposal: proposal.body_markdown });
        }
        this.loading.set(false);
      },
      error: err => {
        this.error.set(err?.error?.detail || 'No se pudo generar la propuesta.');
        this.loading.set(false);
      },
    });
  }

  toPrettyJson(payload: unknown): string {
    return JSON.stringify(payload ?? {}, null, 2);
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandle = setInterval(() => this.pollProgress(), 1500);
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private pollProgress(): void {
    const estimationId = this.runId();
    if (!estimationId) return;

    this.ragService.getGraphProgress(estimationId).subscribe({
      next: progress => {
        this.state.set(progress);
        this.activity.set(progress.activity || []);
        this.syncEditableViews(progress);
        if (progress.state !== 'running') {
          this.stopPolling();
        }
      },
      error: () => {
        this.stopPolling();
      },
    });
  }

  private syncEditableViews(state: GraphRunState): void {
    if (state.pending_gate?.gate === 'structure_review' && this.structureModules().length === 0) {
      const modules = (state.structure?.['modules'] as EditableModule[] | undefined) || [];
      this.structureModules.set(this.cloneModules(modules));
    }

    if (state.pending_gate?.gate === 'final_review' && this.finalModules().length === 0) {
      const modules = (state.estimate?.['modules'] as EditableModule[] | undefined) || [];
      this.finalModules.set(this.cloneModules(modules));
    }

    if (state.state === 'completed') {
      this.stopPolling();
    }
  }

  private cloneModules(modules: EditableModule[]): EditableModule[] {
    return modules.map(module => ({
      name: module.name,
      tasks: (module.tasks || []).map(task => ({
        name: task.name,
        description: task.description,
        estimated_hours: task.estimated_hours,
      })),
    }));
  }
}
