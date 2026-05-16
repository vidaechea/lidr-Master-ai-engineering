import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { EstimationService, SessionListItem } from '../estimation.service';

@Component({
  selector: 'app-sessions-list',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="page">
      <div class="card">
        <!-- Card header -->
        <div class="card-head">
          <div class="head-icon"><mat-icon>history</mat-icon></div>
          <div>
            <h2 class="head-title">Estimation Sessions</h2>
            <p class="head-sub">View and manage your estimation session history</p>
          </div>
        </div>
        <hr class="divider">

        <!-- New session button -->
        <div class="toolbar">
          <button class="btn-primary" (click)="createNewSession()">
            <mat-icon>add</mat-icon>
            <span>New Estimation</span>
          </button>
        </div>

        <!-- Loading state -->
        @if (loading) {
          <div class="loading-container">
            <mat-spinner diameter="40"></mat-spinner>
            <p>Loading sessions...</p>
          </div>
        } @else if (sessions.length === 0) {
          <!-- Empty state -->
          <div class="empty-state">
            <mat-icon class="empty-icon">folder_open</mat-icon>
            <h3>No sessions yet</h3>
            <p>Create a new estimation to get started</p>
            <button class="btn-primary" (click)="createNewSession()">
              <mat-icon>add</mat-icon>
              <span>Create First Estimation</span>
            </button>
          </div>
        } @else {
          <!-- Sessions list -->
          <div class="sessions-container">
            @for (session of sessions; track session.session_id) {
              <div class="session-card" (click)="openSession(session.session_id)">
                <div class="session-header">
                  <div class="session-title">
                    <span class="project-name">{{ session.project_name || 'Unnamed Project' }}</span>
                    <span class="session-id">{{ session.session_id.substring(0, 8) }}...</span>
                  </div>
                  <mat-icon class="session-icon">arrow_forward</mat-icon>
                </div>
                <div class="session-meta">
                  <span class="turns">
                    <mat-icon>chat</mat-icon>
                    {{ session.turn_count }} turn{{ session.turn_count !== 1 ? 's' : '' }}
                  </span>
                </div>
                @if (session.last_message_content) {
                  <div class="session-preview">
                    {{ session.last_message_content }}...
                  </div>
                }
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .page {
      min-height: calc(100vh - 64px);
      background: #f0f0f5;
      padding: 32px 16px;
      margin: -24px -16px;
    }
    .card {
      max-width: 900px;
      margin: 0 auto;
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.08);
      padding: 32px;
    }
    .card-head {
      display: flex;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 24px;
    }
    .head-icon {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      background: #ededf9;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .head-icon mat-icon {
      color: #5c6bc0;
      font-size: 26px;
      width: 26px;
      height: 26px;
    }
    .head-title {
      margin: 0 0 4px;
      font-size: 1.5rem;
      font-weight: 700;
      color: #1a1a2e;
    }
    .head-sub {
      margin: 0;
      font-size: 0.875rem;
      color: #777;
    }
    .divider {
      border: none;
      border-top: 1px solid #f0f0f0;
      margin: 0 0 28px;
    }

    .toolbar {
      display: flex;
      justify-content: flex-end;
      margin-bottom: 24px;
    }
    .btn-primary {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 12px 28px;
      border-radius: 10px;
      background: #5c6bc0;
      color: #fff;
      font-size: 0.9rem;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: background .2s, box-shadow .2s;
      box-shadow: 0 2px 8px rgba(92,107,192,0.3);
    }
    .btn-primary:hover {
      background: #3f51b5;
      box-shadow: 0 4px 12px rgba(92,107,192,0.4);
    }
    .btn-primary mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }

    .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 60px 20px;
      gap: 16px;
    }
    .loading-container p {
      color: #666;
      font-size: 0.9rem;
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 60px 20px;
      text-align: center;
    }
    .empty-icon {
      font-size: 64px;
      width: 64px;
      height: 64px;
      color: #ddd;
      margin-bottom: 16px;
    }
    .empty-state h3 {
      margin: 0 0 8px;
      font-size: 1.2rem;
      color: #333;
    }
    .empty-state p {
      margin: 0 0 24px;
      color: #777;
      font-size: 0.9rem;
    }

    .sessions-container {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 16px;
    }
    .session-card {
      border: 1.5px solid #e8e8f0;
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all .2s;
      background: #fff;
    }
    .session-card:hover {
      border-color: #5c6bc0;
      box-shadow: 0 4px 16px rgba(92,107,192,0.15);
      transform: translateY(-2px);
    }
    .session-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .session-title {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .project-name {
      font-weight: 600;
      color: #333;
      font-size: 0.95rem;
    }
    .session-id {
      font-size: 0.75rem;
      color: #999;
      font-family: monospace;
    }
    .session-icon {
      color: #5c6bc0;
      font-size: 20px;
      width: 20px;
      height: 20px;
      opacity: 0;
      transition: opacity .2s, transform .2s;
    }
    .session-card:hover .session-icon {
      opacity: 1;
      transform: translateX(4px);
    }
    .session-meta {
      display: flex;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 0.8rem;
      color: #666;
    }
    .session-meta .turns {
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .session-meta mat-icon {
      font-size: 14px;
      width: 14px;
      height: 14px;
    }
    .session-preview {
      font-size: 0.8rem;
      color: #777;
      line-height: 1.4;
      max-height: 60px;
      overflow: hidden;
      text-overflow: ellipsis;
      border-top: 1px solid #f0f0f0;
      padding-top: 12px;
    }
  `],
})
export class SessionsListComponent implements OnInit {
  sessions: SessionListItem[] = [];
  loading = true;

  constructor(
    private readonly estimationService: EstimationService,
    private readonly router: Router,
  ) {}

  ngOnInit() {
    this.loadSessions();
  }

  loadSessions() {
    this.loading = true;
    this.estimationService.listSessions().subscribe({
      next: sessions => {
        this.sessions = sessions;
        this.loading = false;
      },
      error: () => {
        this.sessions = [];
        this.loading = false;
      },
    });
  }

  createNewSession() {
    this.router.navigate(['/estimations/new']);
  }

  openSession(sessionId: string) {
    this.router.navigate(['/estimations', sessionId]);
  }
}
