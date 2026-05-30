import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly _user = signal<UserOut | null>(null);
  readonly user = this._user.asReadonly();
  readonly isLoggedIn = computed(() => this._user() !== null);

  constructor(private readonly http: HttpClient, private readonly router: Router) {
    // Restore session on page load if a token is present.
    if (this.accessToken) {
      this.fetchCurrentUser().subscribe({ error: () => this.clearTokens() });
    }
  }

  get accessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  register(email: string, password: string, full_name?: string) {
    return this.http
      .post<TokenResponse>(`${environment.apiUrl}/v1/auth/register`, { email, password, full_name })
      .pipe(tap(t => this.storeTokensAndFetchUser(t)));
  }

  login(email: string, password: string) {
    // FastAPI OAuth2PasswordRequestForm expects form data.
    const body = new URLSearchParams({ username: email, password });
    return this.http
      .post<TokenResponse>(`${environment.apiUrl}/v1/auth/login`, body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .pipe(tap(t => this.storeTokensAndFetchUser(t)));
  }

  refresh() {
    const refresh_token = localStorage.getItem(REFRESH_KEY);
    if (!refresh_token) throw new Error('No refresh token');
    return this.http
      .post<TokenResponse>(`${environment.apiUrl}/v1/auth/refresh`, { refresh_token })
      .pipe(tap(t => this.storeTokens(t)));
  }

  logout() {
    this.clearTokens();
    this._user.set(null);
    this.router.navigate(['/auth/login']);
  }

  fetchCurrentUser() {
    return this.http
      .get<UserOut>(`${environment.apiUrl}/v1/auth/me`)
      .pipe(tap(u => this._user.set(u)));
  }

  private storeTokensAndFetchUser(tokens: TokenResponse) {
    this.storeTokens(tokens);
    this.fetchCurrentUser().subscribe();
  }

  private storeTokens(tokens: TokenResponse) {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }

  private clearTokens() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }
}
