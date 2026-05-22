import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { of, throwError } from 'rxjs';

import { authInterceptor } from './auth.interceptor';
import { AuthService, TokenResponse } from './auth.service';

const MOCK_TOKENS: TokenResponse = {
  access_token: 'new.access.token',
  refresh_token: 'new.refresh.token',
  token_type: 'bearer',
};

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authMock: {
    accessToken: string | null;
    refresh: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    authMock = {
      accessToken: 'initial.access.token',
      refresh: vi.fn().mockReturnValue(of(MOCK_TOKENS)),
      logout: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: authMock },
      ],
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  // ── Token attachment ───────────────────────────────────────────────────────

  it('adds Authorization: Bearer header when access token is present', () => {
    http.get('/api/resource').subscribe();

    const req = httpMock.expectOne('/api/resource');
    expect(req.request.headers.get('Authorization')).toBe(
      'Bearer initial.access.token',
    );
    req.flush({});
  });

  it('does not add Authorization header when no access token', () => {
    authMock.accessToken = null;

    http.get('/api/resource').subscribe();

    const req = httpMock.expectOne('/api/resource');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  // ── 401 → refresh + retry ─────────────────────────────────────────────────

  it('calls auth.refresh() and retries the original request on 401', () => {
    http.get('/api/protected').subscribe({ error: () => {} });

    // First attempt returns 401
    const firstReq = httpMock.expectOne('/api/protected');
    firstReq.flush(
      { detail: 'Unauthorized' },
      { status: 401, statusText: 'Unauthorized' },
    );

    // Interceptor called refresh, then retried
    expect(authMock.refresh).toHaveBeenCalledTimes(1);
    const retryReq = httpMock.expectOne('/api/protected');
    retryReq.flush({ data: 'ok' });
  });

  it('retried request carries a fresh Authorization header', () => {
    authMock.accessToken = 'new.access.token'; // value after mock refresh
    http.get('/api/protected').subscribe({ error: () => {} });

    const firstReq = httpMock.expectOne('/api/protected');
    firstReq.flush(
      { detail: 'Unauthorized' },
      { status: 401, statusText: 'Unauthorized' },
    );

    const retryReq = httpMock.expectOne('/api/protected');
    expect(retryReq.request.headers.get('Authorization')).toBe(
      'Bearer new.access.token',
    );
    retryReq.flush({});
  });

  it('calls auth.logout() when the refresh attempt fails', () => {
    authMock.refresh = vi
      .fn()
      .mockReturnValue(throwError(() => new Error('Refresh failed')));

    http.get('/api/protected').subscribe({ error: () => {} });

    const req = httpMock.expectOne('/api/protected');
    req.flush(
      { detail: 'Unauthorized' },
      { status: 401, statusText: 'Unauthorized' },
    );

    expect(authMock.logout).toHaveBeenCalledTimes(1);
  });

  // ── Non-401 errors ────────────────────────────────────────────────────────

  it('does not call refresh for non-401 errors', () => {
    http.get('/api/resource').subscribe({ error: () => {} });

    const req = httpMock.expectOne('/api/resource');
    req.flush({ detail: 'Not found' }, { status: 404, statusText: 'Not Found' });

    expect(authMock.refresh).not.toHaveBeenCalled();
    expect(authMock.logout).not.toHaveBeenCalled();
  });

  it('propagates non-401 errors to the subscriber', () => {
    let capturedStatus: number | null = null;

    http.get('/api/resource').subscribe({
      error: err => (capturedStatus = err.status),
    });

    httpMock
      .expectOne('/api/resource')
      .flush({ detail: 'Server error' }, { status: 500, statusText: 'Internal Server Error' });

    expect(capturedStatus).toBe(500);
  });
});
