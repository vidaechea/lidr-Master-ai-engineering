import { Component, OnInit, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { EstimationService, SessionListItem } from '../estimation.service';

@Component({
  selector: 'app-sessions-list',
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatIconModule, MatChipsModule],
  template: `
    <div class="page-header">
      <h1>Estimation Sessions</h1>
      <div class="header-actions">
        <button mat-stroked-button color="primary" (click)="goToRagForm()">
          <mat-icon>psychology</mat-icon> RAG Form
        </button>
        <button mat-raised-button color="primary" (click)="createNewSession()">
          <mat-icon>add</mat-icon> New Estimation
        </button>
      </div>
    </div>

    @if (loading()) {
      <p>Loading…</p>
    } @else if (sessions().length === 0) {
      <mat-card class="empty-state">
        <mat-card-content>
          <p>No sessions yet. Create your first estimation to start.</p>
        </mat-card-content>
      </mat-card>
    } @else {
      <div class="sessions-grid">
        @for (session of sessions(); track session.session_id) {
          <mat-card class="session-card">
            <mat-card-header>
              <mat-card-title>{{ session.project_name || 'Unnamed Project' }}</mat-card-title>
              <mat-chip-set>
                <mat-chip>{{ session.turn_count }} turn{{ session.turn_count !== 1 ? 's' : '' }}</mat-chip>
              </mat-chip-set>
            </mat-card-header>
            <mat-card-content>
              <p>{{ session.last_message_content || 'No messages yet.' }}</p>
              <small>Session {{ session.session_id.substring(0, 8) }}...</small>
            </mat-card-content>
            <mat-card-actions>
              <button mat-button type="button" (click)="openSession(session.session_id)">Continue</button>
            </mat-card-actions>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
    .header-actions { display:flex; gap:12px; align-items:center; }
    .sessions-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px,1fr)); gap:16px; }
    .session-card { cursor:default; }
    .empty-state { padding:32px; text-align:center; }
  `],
})
export class SessionsListComponent implements OnInit {
  sessions = signal<SessionListItem[]>([]);
  loading = signal(true);

  constructor(
    private readonly estimationService: EstimationService,
    private readonly router: Router,
  ) {}

  ngOnInit() {
    this.loadSessions();
  }

  loadSessions() {
    this.loading.set(true);
    this.estimationService.listSessions().subscribe({
      next: sessions => {
        this.sessions.set(sessions);
        this.loading.set(false);
      },
      error: () => {
        this.sessions.set([]);
        this.loading.set(false);
      },
    });
  }

  createNewSession() {
    this.router.navigate(['/estimations/new']);
  }

  goToRagForm() {
    this.router.navigate(['/estimations/rag-form']);
  }

  openSession(sessionId: string) {
    this.router.navigate(['/estimations', sessionId]);
  }
}
