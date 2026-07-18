import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { Router } from '@angular/router';

interface GraphNodeView {
  key: string;
  label: string;
  kind: 'agent' | 'gate' | 'fanout' | 'join';
  model: string;
  role: string;
  explanation: string;
  edge: string;
}

@Component({
  selector: 'app-graph-flow',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule],
  template: `
    <div class="page">
      <div class="header">
        <h1>Flujo agentico de estimación</h1>
        <button mat-stroked-button color="primary" (click)="goToRun()">Probar flujo</button>
      </div>

      <mat-card class="summary">
        <mat-card-content>
          <p>
            Este proceso usa dos handovers (<strong>Command goto</strong>), dos puertas humanas
            (<strong>structure review</strong> y <strong>final review</strong>) y fan-out para estimar
            horas por tarea en paralelo.
          </p>
        </mat-card-content>
      </mat-card>

      <div class="legend">
        <span>handover</span>
        <span>gate humano</span>
        <span>fan-out</span>
        <span>join</span>
      </div>

      <div class="nodes">
        @for (node of nodes; track node.key) {
          <mat-card class="node" [class]="'kind-' + node.kind">
            <mat-card-header>
              <mat-card-title>{{ node.label }}</mat-card-title>
              <mat-card-subtitle>{{ node.role }}</mat-card-subtitle>
            </mat-card-header>
            <mat-card-content>
              <p class="model">{{ node.model }}</p>
              <p>{{ node.explanation }}</p>
              <p class="edge">Salida: {{ node.edge }}</p>
            </mat-card-content>
          </mat-card>
        }
      </div>
    </div>
  `,
  styles: [
    `
      .page { max-width: 980px; margin: 0 auto; padding: 24px; }
      .header { display:flex; justify-content:space-between; align-items:center; gap: 16px; margin-bottom: 16px; }
      .summary { margin-bottom: 16px; }
      .legend { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; font-size:12px; color:#5b6470; }
      .legend span { border: 1px solid #d0d7de; border-radius: 12px; padding: 4px 10px; }
      .nodes { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
      .node { border-width: 2px; border-style: solid; }
      .kind-agent { border-color: #7ea0ff; }
      .kind-gate { border-color: #f2bd5c; }
      .kind-fanout { border-color: #63c5da; }
      .kind-join { border-color: #8e95a1; }
      .model { font-size: 12px; color: #667085; margin-bottom: 8px; }
      .edge { font-size: 12px; font-weight: 600; margin-top: 10px; color: #445; }
    `,
  ],
})
export class GraphFlowComponent {
  readonly nodes: GraphNodeView[] = [
    {
      key: 'classifier',
      label: 'Classifier',
      kind: 'agent',
      model: 'gpt-4o-mini',
      role: 'Clasifica complejidad y reformula el brief',
      explanation: 'Analiza la transcripción inicial para ajustar el nivel de esfuerzo del flujo.',
      edge: 'handover a Structure',
    },
    {
      key: 'structure',
      label: 'Structure',
      kind: 'agent',
      model: 'gpt-5.x',
      role: 'Propone módulos y tareas',
      explanation: 'Genera un desglose editable de módulos y tareas sin horas.',
      edge: 'arista a Gate 1',
    },
    {
      key: 'gate-1',
      label: 'Gate 1: Structure Review',
      kind: 'gate',
      model: 'sin LLM',
      role: 'Validación humana del desglose',
      explanation: 'Permite editar y aprobar módulos/tareas antes de estimar horas.',
      edge: 'fan-out de Hours',
    },
    {
      key: 'hours',
      label: 'Hours x N',
      kind: 'fanout',
      model: 'determinístico + retrieval',
      role: 'Estimación por tarea en paralelo',
      explanation: 'Cada tarea ejecuta su búsqueda y consenso histórico en paralelo.',
      edge: 'join en Recover',
    },
    {
      key: 'recover',
      label: 'Recover & Handover',
      kind: 'join',
      model: 'gpt-5.x',
      role: 'Consolida y recupera casos dudosos',
      explanation: 'Une resultados, completa vacíos y prepara la estimación agregada.',
      edge: 'handover a Analysis',
    },
    {
      key: 'analysis',
      label: 'Analysis',
      kind: 'agent',
      model: 'gpt-4o',
      role: 'Informe de fiabilidad',
      explanation: 'Genera reporte de fiabilidad sin alterar las cifras consolidadas.',
      edge: 'arista a Gate 2',
    },
    {
      key: 'gate-2',
      label: 'Gate 2: Final Review',
      kind: 'gate',
      model: 'sin LLM',
      role: 'Validación final humana',
      explanation: 'Permite ajustar horas y confirmar status final validated/needs_review.',
      edge: 'proposal o end',
    },
  ];

  constructor(private readonly router: Router) {}

  goToRun(): void {
    this.router.navigate(['/estimations/graph-run']);
  }
}
