import { Routes } from '@angular/router';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/projects', pathMatch: 'full' },

  // ── Auth ──────────────────────────────────────────────────────────────────
  {
    path: 'auth',
    children: [
      {
        path: 'login',
        loadComponent: () =>
          import('./features/auth/login/login.component').then(m => m.LoginComponent),
      },
      {
        path: 'register',
        loadComponent: () =>
          import('./features/auth/register/register.component').then(m => m.RegisterComponent),
      },
      { path: '', redirectTo: 'login', pathMatch: 'full' },
    ],
  },

  // ── Projects (protected) ──────────────────────────────────────────────────
  {
    path: 'projects',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/projects/project-list/project-list.component').then(
            m => m.ProjectListComponent,
          ),
      },
    ],
  },

  // ── Estimations (protected) ───────────────────────────────────────────────
  {
    path: 'estimations',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/estimations/sessions-list/sessions-list.component').then(
            m => m.SessionsListComponent,
          ),
      },
      {
        path: 'new',
        loadComponent: () =>
          import('./features/estimations/estimation-form/estimation-form.component').then(
            m => m.EstimationFormComponent,
          ),
      },
      {
        path: ':sessionId',
        loadComponent: () =>
          import('./features/estimations/estimation-form/estimation-form.component').then(
            m => m.EstimationFormComponent,
          ),
      },
    ],
  },

  { path: '**', redirectTo: '/projects' },
];
