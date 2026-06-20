import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '../../../core/auth/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule, RouterLink, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule],
  template: `
    <div class="auth-container">
      <mat-card class="auth-card">
        <mat-card-header><mat-card-title>Create account</mat-card-title></mat-card-header>
        <mat-card-content>
          <form (ngSubmit)="submit()" #f="ngForm">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Full name</mat-label>
              <input matInput name="fullName" [(ngModel)]="fullName" />
            </mat-form-field>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Email</mat-label>
              <input matInput type="email" name="email" [(ngModel)]="email" required />
            </mat-form-field>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Password</mat-label>
              <input matInput type="password" name="password" [(ngModel)]="password" required minlength="8" />
            </mat-form-field>
            @if (error()) {
              <p class="error-msg">{{ error() }}</p>
            }
            <button mat-raised-button color="primary" type="submit" class="full-width">Register</button>
          </form>
        </mat-card-content>
        <mat-card-actions>
          <span>Already have an account? <a routerLink="/auth/login">Sign in</a></span>
        </mat-card-actions>
      </mat-card>
    </div>
  `,
  styles: [`
    .auth-container { display:flex; justify-content:center; align-items:center; height:100vh; }
    .auth-card { width:400px; padding:16px; }
    .full-width { width:100%; margin-bottom:12px; }
    .error-msg { color:var(--mat-sys-error); font-size:0.875rem; }
  `],
})
export class RegisterComponent {
  fullName = '';
  email = '';
  password = '';
  error = signal<string | null>(null);

  constructor(private auth: AuthService, private router: Router) {}

  submit() {
    this.error.set(null);
    this.auth.register(this.email, this.password, this.fullName || undefined).subscribe({
      next: () => this.router.navigate(['/projects']),
      error: () => this.error.set('Registration failed. Try a different email.'),
    });
  }
}
