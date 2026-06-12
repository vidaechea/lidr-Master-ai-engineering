import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatChipsModule } from '@angular/material/chips';
import { DatePipe } from '@angular/common';
import { Project, ProjectService } from '../project.service';

@Component({
  selector: 'app-project-list',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatDialogModule, MatChipsModule, DatePipe],
  template: `
    <div class="page-header">
      <h1>Projects</h1>
      <button mat-raised-button color="primary" routerLink="/projects/new">
        <mat-icon>add</mat-icon> New Project
      </button>
    </div>

    @if (loading()) {
      <p>Loading…</p>
    } @else if (projects().length === 0) {
      <mat-card class="empty-state">
        <mat-card-content>
          <p>No projects yet. Create your first project to start estimating.</p>
        </mat-card-content>
      </mat-card>
    } @else {
      <div class="projects-grid">
        @for (project of projects(); track project.id) {
          <mat-card class="project-card">
            <mat-card-header>
              <mat-card-title>{{ project.name }}</mat-card-title>
              @if (project.project_type) {
                <mat-chip-set>
                  <mat-chip>{{ project.project_type }}</mat-chip>
                </mat-chip-set>
              }
            </mat-card-header>
            <mat-card-content>
              <p>{{ project.description || 'No description' }}</p>
              <small>Created {{ project.created_at | date:'mediumDate' }}</small>
            </mat-card-content>
            <mat-card-actions>
              <a mat-button [routerLink]="['/projects', project.id]">View</a>
              <a mat-button [routerLink]="['/estimations/new']" [queryParams]="{projectId: project.id}">
                New Estimation
              </a>
            </mat-card-actions>
          </mat-card>
        }
      </div>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
    .projects-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px,1fr)); gap:16px; }
    .project-card { cursor:default; }
    .empty-state { padding:32px; text-align:center; }
  `],
})
export class ProjectListComponent implements OnInit {
  projects = signal<Project[]>([]);
  loading = signal(true);

  constructor(private projectService: ProjectService) {}

  ngOnInit() {
    this.projectService.load().subscribe({
      next: (p: Project[]) => { this.projects.set(p); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
