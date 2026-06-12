import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';

import { AuthService, TokenResponse } from './auth.service';
import { environment } from '../../../environments/environment';

const API = environment.apiUrl;

const MOCK_TOKENS: TokenResponse = {
  access_token: 'access.tok.en',
  refresh_token: 'refresh.tok.en',
  token_type: 'bearer',
};

const MOCK_USER = {
  id: 'user-001',
  email: 'alice@example.com',
  full_name: 'Alice',
  is_active: true,
  created_at: '2026-05-15T10:00:00Z',
};

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  // ── register() ────────────────────────────────────────────────────────────

  describe('register()', () => {
    it('sends POST /v1/auth/register with JSON body', () => {
      service.register('alice@example.com', 'Pass123!', 'Alice').subscribe();

      const req = httpMock.expectOne(`${API}/v1/auth/register`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({
        email: 'alice@example.com',
        password: 'Pass123!',
        full_name: 'Alice',
      });
      req.flush(MOCK_TOKENS);
      // storeTokensAndFetchUser triggers GET /me
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);
    });

    it('stores access_token and refresh_token in localStorage', () => {
      service.register('alice@example.com', 'Pass123!').subscribe();
      httpMock.expectOne(`${API}/v1/auth/register`).flush(MOCK_TOKENS);
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);

      expect(localStorage.getItem('access_token')).toBe(MOCK_TOKENS.access_token);
      expect(localStorage.getItem('refresh_token')).toBe(MOCK_TOKENS.refresh_token);
    });

    it('updates the user signal after successful registration', () => {
      service.register('alice@example.com', 'Pass123!').subscribe();
      httpMock.expectOne(`${API}/v1/auth/register`).flush(MOCK_TOKENS);
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);

      expect(service.user()?.email).toBe('alice@example.com');
      expect(service.isLoggedIn()).toBe(true);
    });
  });

  // ── login() ───────────────────────────────────────────────────────────────

  describe('login()', () => {
    it('sends POST /v1/auth/login with form-encoded body', () => {
      service.login('alice@example.com', 'Pass123!').subscribe();

      const req = httpMock.expectOne(`${API}/v1/auth/login`);
      expect(req.request.method).toBe('POST');
      expect(req.request.headers.get('Content-Type')).toBe(
        'application/x-www-form-urlencoded',
      );
      // @ is encoded as %40 in URLSearchParams
      expect(req.request.body).toContain('username=alice%40example.com');
      req.flush(MOCK_TOKENS);
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);
    });

    it('stores tokens on successful login', () => {
      service.login('alice@example.com', 'Pass123!').subscribe();
      httpMock.expectOne(`${API}/v1/auth/login`).flush(MOCK_TOKENS);
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);

      expect(localStorage.getItem('access_token')).toBe(MOCK_TOKENS.access_token);
    });

    it('updates the user signal after successful login', () => {
      service.login('alice@example.com', 'Pass123!').subscribe();
      httpMock.expectOne(`${API}/v1/auth/login`).flush(MOCK_TOKENS);
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);

      expect(service.user()?.email).toBe('alice@example.com');
    });
  });

  // ── refresh() ─────────────────────────────────────────────────────────────

  describe('refresh()', () => {
    it('sends POST /v1/auth/refresh with the stored refresh token', () => {
      localStorage.setItem('refresh_token', 'old.refresh.token');

      service.refresh().subscribe();

      const req = httpMock.expectOne(`${API}/v1/auth/refresh`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ refresh_token: 'old.refresh.token' });
      req.flush(MOCK_TOKENS);
    });

    it('updates access_token in localStorage after refresh', () => {
      localStorage.setItem('refresh_token', 'old.refresh.token');
      service.refresh().subscribe();
      httpMock.expectOne(`${API}/v1/auth/refresh`).flush(MOCK_TOKENS);

      expect(localStorage.getItem('access_token')).toBe(MOCK_TOKENS.access_token);
    });

    it('throws synchronously when no refresh token is stored', () => {
      expect(() => service.refresh()).toThrow('No refresh token');
    });
  });

  // ── logout() ──────────────────────────────────────────────────────────────

  describe('logout()', () => {
    it('clears access_token and refresh_token from localStorage', () => {
      localStorage.setItem('access_token', 'tok');
      localStorage.setItem('refresh_token', 'ref');
      vi.spyOn(router, 'navigate').mockResolvedValue(true);

      service.logout();

      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
    });

    it('sets user signal to null', () => {
      vi.spyOn(router, 'navigate').mockResolvedValue(true);
      service.logout();
      expect(service.user()).toBeNull();
    });

    it('navigates to /auth/login', () => {
      const navSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
      service.logout();
      expect(navSpy).toHaveBeenCalledWith(['/auth/login']);
    });
  });

  // ── fetchCurrentUser() ────────────────────────────────────────────────────

  describe('fetchCurrentUser()', () => {
    it('sends GET /v1/auth/me', () => {
      service.fetchCurrentUser().subscribe();

      const req = httpMock.expectOne(`${API}/v1/auth/me`);
      expect(req.request.method).toBe('GET');
      req.flush(MOCK_USER);
    });

    it('updates user signal with the server response', () => {
      service.fetchCurrentUser().subscribe();
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);

      expect(service.user()?.id).toBe('user-001');
      expect(service.user()?.email).toBe('alice@example.com');
    });
  });

  // ── accessToken getter ────────────────────────────────────────────────────

  describe('accessToken', () => {
    it('returns null when localStorage is empty', () => {
      expect(service.accessToken).toBeNull();
    });

    it('returns the stored token', () => {
      localStorage.setItem('access_token', 'my.access.token');
      expect(service.accessToken).toBe('my.access.token');
    });
  });

  // ── isLoggedIn computed ───────────────────────────────────────────────────

  describe('isLoggedIn', () => {
    it('is false when user signal is null', () => {
      expect(service.isLoggedIn()).toBe(false);
    });

    it('is true after fetchCurrentUser succeeds', () => {
      service.fetchCurrentUser().subscribe();
      httpMock.expectOne(`${API}/v1/auth/me`).flush(MOCK_USER);
      expect(service.isLoggedIn()).toBe(true);
    });
  });
});
