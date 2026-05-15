import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { AuthService } from '../../../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatDividerModule,
  ],
  template: `
    <div class="auth-container">
      <mat-card class="auth-card">
        <mat-card-header>
          <mat-card-title>Sign in</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <form (ngSubmit)="submit()" #f="ngForm">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Email</mat-label>
              <input matInput type="email" name="email" [(ngModel)]="email" required />
            </mat-form-field>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Password</mat-label>
              <input matInput type="password" name="password" [(ngModel)]="password" required />
            </mat-form-field>
            @if (error()) {
              <p class="error-msg">{{ error() }}</p>
            }
            <button mat-raised-button color="primary" type="submit" class="full-width">
              Sign in
            </button>
          </form>
          <mat-divider class="divider" />
          <button mat-stroked-button class="full-width google-btn" (click)="loginGoogle()">
            Sign in with Google
          </button>
        </mat-card-content>
        <mat-card-actions>
          <span>No account? <a routerLink="/auth/register">Register</a></span>
        </mat-card-actions>
      </mat-card>
    </div>
  `,
  styles: [`
    .auth-container { display:flex; justify-content:center; align-items:center; height:100vh; }
    .auth-card { width:400px; padding:16px; }
    .full-width { width:100%; margin-bottom:12px; }
    .divider { margin:16px 0; }
    .google-btn { margin-top:8px; }
    .error-msg { color:var(--mat-sys-error); font-size:0.875rem; margin-bottom:8px; }
  `],
})
export class LoginComponent {
  email = '';
  password = '';
  error = signal<string | null>(null);

  constructor(private auth: AuthService, private router: Router) {}

  submit() {
    this.error.set(null);
    this.auth.login(this.email, this.password).subscribe({
      next: () => this.router.navigate(['/projects']),
      error: () => this.error.set('Invalid email or password'),
    });
  }

  loginGoogle() {
    this.auth.loginWithGoogle();
  }
}
