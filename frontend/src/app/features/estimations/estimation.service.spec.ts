import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import {
  EstimationService,
  EstimationCreate,
  EstimationOut,
  GuardrailError,
  SessionEstimationResponse,
} from './estimation.service';
import { environment } from '../../../environments/environment';

const BASE = `${environment.apiUrl}/v1/estimations`;
const SESSIONS_BASE = `${environment.apiUrl}/v1/estimations/sessions`;

const MOCK_ESTIMATION: EstimationOut = {
  id: 'est-001',
  project_id: null,
  status: 'completed',
  model_used: 'gpt-4o-mini',
  total_cost_usd: 0.0006,
  created_at: '2026-05-15T10:00:00Z',
  completed_at: '2026-05-15T10:00:05Z',
  transcription:
    'A B2B SaaS company needs an admin portal to manage their existing customer accounts.',
  prompt_version: 'v1',
  estimation_markdown: '## Admin Portal\n1. Auth & SSO: 40h\n**Total: 40h**',
  structured_result: null,
  requirements: '- SSO\n- User list\n- Audit log',
  validation_result: null,
  input_tokens: 450,
  output_tokens: 180,
  turn_cost_usd: 0.0006,
  error_detail: null,
};

const VALID_PAYLOAD: EstimationCreate = {
  transcription:
    'A B2B SaaS company needs an admin portal to manage their existing customer accounts.',
  output_format: 'phases_table',
  prompt_version: 'v1',
  pre_call: false,
  num_examples: 3,
  max_output_tokens: 2048,
};

describe('EstimationService', () => {
  let service: EstimationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(EstimationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  // ── list() ────────────────────────────────────────────────────────────────

  describe('list()', () => {
    it('sends GET /v1/estimations without query params', () => {
      service.list().subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.keys().length).toBe(0);
      req.flush([MOCK_ESTIMATION]);
    });

    it('includes project_id query param when provided', () => {
      service.list('proj-123').subscribe();

      const req = httpMock.expectOne(r => r.url === BASE);
      expect(req.request.params.get('project_id')).toBe('proj-123');
      req.flush([MOCK_ESTIMATION]);
    });

    it('returns the deserialized estimation list', () => {
      let result: unknown;
      service.list().subscribe(r => (result = r));
      httpMock.expectOne(BASE).flush([MOCK_ESTIMATION]);

      expect(result).toEqual([MOCK_ESTIMATION]);
    });
  });

  // ── get() ─────────────────────────────────────────────────────────────────

  describe('get()', () => {
    it('sends GET /v1/estimations/{id}', () => {
      service.get('est-001').subscribe();

      const req = httpMock.expectOne(`${BASE}/est-001`);
      expect(req.request.method).toBe('GET');
      req.flush(MOCK_ESTIMATION);
    });

    it('returns the full EstimationOut object', () => {
      let result: unknown;
      service.get('est-001').subscribe(r => (result = r));
      httpMock.expectOne(`${BASE}/est-001`).flush(MOCK_ESTIMATION);

      expect((result as EstimationOut).estimation_markdown).toBe(
        MOCK_ESTIMATION.estimation_markdown,
      );
    });
  });

  // ── create() ──────────────────────────────────────────────────────────────

  describe('create()', () => {
    it('sends POST /v1/estimations with the full payload', () => {
      service.create(VALID_PAYLOAD).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(VALID_PAYLOAD);
      req.flush(MOCK_ESTIMATION);
    });

    it('includes optional project_id when provided', () => {
      const withProject: EstimationCreate = { ...VALID_PAYLOAD, project_id: 'proj-001' };
      service.create(withProject).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.body.project_id).toBe('proj-001');
      req.flush(MOCK_ESTIMATION);
    });

    it('returns the completed estimation with markdown', () => {
      let result: EstimationOut | undefined;
      service.create(VALID_PAYLOAD).subscribe(r => (result = r));
      httpMock.expectOne(BASE).flush(MOCK_ESTIMATION);

      expect(result?.status).toBe('completed');
      expect(result?.estimation_markdown).toContain('Admin Portal');
    });
  });

  // ── createAsync() ─────────────────────────────────────────────────────────

  describe('createAsync()', () => {
    it('sends POST /v1/estimations/async', () => {
      service.createAsync(VALID_PAYLOAD).subscribe();

      const req = httpMock.expectOne(`${BASE}/async`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(VALID_PAYLOAD);
      req.flush({ estimation_id: 'est-001', job_id: 'job-abc123', status: 'pending' });
    });

    it('returns estimation_id, job_id, and pending status', () => {
      let result: { estimation_id: string; job_id: string; status: string } | undefined;
      service.createAsync(VALID_PAYLOAD).subscribe(r => (result = r));

      httpMock
        .expectOne(`${BASE}/async`)
        .flush({ estimation_id: 'est-001', job_id: 'job-abc123', status: 'pending' });

      expect(result?.status).toBe('pending');
      expect(result?.job_id).toBe('job-abc123');
    });
  });

  // ── pollStatus() ──────────────────────────────────────────────────────────

  describe('pollStatus()', () => {
    it('sends GET /v1/estimations/{id}/status', () => {
      service.pollStatus('est-001').subscribe();

      const req = httpMock.expectOne(`${BASE}/est-001/status`);
      expect(req.request.method).toBe('GET');
      req.flush({ id: 'est-001', status: 'completed', completed_at: '2026-05-15T10:00:05Z' });
    });

    it('returns the status, id, and completed_at fields', () => {
      let result: { id: string; status: string; completed_at: string | null } | undefined;
      service.pollStatus('est-001').subscribe(r => (result = r));

      httpMock.expectOne(`${BASE}/est-001/status`).flush({
        id: 'est-001',
        status: 'completed',
        completed_at: '2026-05-15T10:00:05Z',
      });

      expect(result?.status).toBe('completed');
      expect(result?.id).toBe('est-001');
    });

    it('reflects processing status for an in-progress estimation', () => {
      let result: { status: string } | undefined;
      service.pollStatus('est-002').subscribe(r => (result = r));

      httpMock.expectOne(`${BASE}/est-002/status`).flush({
        id: 'est-002',
        status: 'processing',
        completed_at: null,
      });

      expect(result?.status).toBe('processing');
    });
  });

  // ── GuardrailError shape ───────────────────────────────────────────────────

  describe('GuardrailError type contract', () => {
    it('create() error body with reason=pii matches GuardrailError shape', () => {
      let caughtError: unknown;
      service.create(VALID_PAYLOAD).subscribe({ error: e => (caughtError = e) });

      httpMock.expectOne(BASE).flush(
        { detail: { message: 'Email address detected.', reason: 'pii' } },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

      const detail = (caughtError as { error: { detail: GuardrailError } }).error.detail;
      expect(detail.reason).toBe('pii');
      expect(detail.message).toContain('Email');
    });

    it('create() error body with reason=prompt_injection matches GuardrailError shape', () => {
      let caughtError: unknown;
      service.create(VALID_PAYLOAD).subscribe({ error: e => (caughtError = e) });

      httpMock.expectOne(BASE).flush(
        { detail: { message: 'Suspicious text.', reason: 'prompt_injection' } },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

      const detail = (caughtError as { error: { detail: GuardrailError } }).error.detail;
      expect(detail.reason).toBe('prompt_injection');
    });

    it('create() error body with reason=moderation matches GuardrailError shape', () => {
      let caughtError: unknown;
      service.create(VALID_PAYLOAD).subscribe({ error: e => (caughtError = e) });

      httpMock.expectOne(BASE).flush(
        { detail: { message: 'Input flagged by moderation: hate', reason: 'moderation' } },
        { status: 400, statusText: 'Bad Request' },
      );

      const detail = (caughtError as { error: { detail: GuardrailError } }).error.detail;
      expect(detail.reason).toBe('moderation');
    });
  });

  // ── create() with ACB mode ─────────────────────────────────────────────────

  describe('create() with ACB mode', () => {
    it('includes estimation_mode=acb in request body', () => {
      const acbPayload: EstimationCreate = { ...VALID_PAYLOAD, estimation_mode: 'acb' };
      service.create(acbPayload).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.body.estimation_mode).toBe('acb');
      req.flush(MOCK_ESTIMATION);
    });

    it('includes acb_max_iterations in request body when provided', () => {
      const acbPayload: EstimationCreate = {
        ...VALID_PAYLOAD,
        estimation_mode: 'acb',
        acb_max_iterations: 1,
      };
      service.create(acbPayload).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.body.acb_max_iterations).toBe(1);
      req.flush(MOCK_ESTIMATION);
    });

    it('routes to the same /v1/estimations endpoint as standard mode', () => {
      const acbPayload: EstimationCreate = {
        ...VALID_PAYLOAD,
        estimation_mode: 'acb',
        acb_max_iterations: 2,
      };
      service.create(acbPayload).subscribe();

      // Same base URL — the backend dispatches based on estimation_mode
      const req = httpMock.expectOne(BASE);
      expect(req.request.method).toBe('POST');
      req.flush(MOCK_ESTIMATION);
    });
  });
});

// ---------------------------------------------------------------------------
// Session-based estimation (attachment path)
// ---------------------------------------------------------------------------

const MOCK_SESSION_RESPONSE: SessionEstimationResponse = {
  estimation: '## Phase 1\n40h',
  model: 'gpt-4o-mini',
  response_id: 'resp-abc',
  input_tokens: 320,
  output_tokens: 90,
  turn_cost_usd: 0.000035,
  total_cost_usd: 0.000035,
  estimated_input_tokens: 300,
  estimated_precall_cost_usd: null,
  requirements: null,
  pre_call_cost_usd: null,
  prompt_version: 'v1',
};

describe('EstimationService — createSession()', () => {
  let service: EstimationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(EstimationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('sends POST to the sessions base URL', () => {
    service.createSession().subscribe();

    const req = httpMock.expectOne(SESSIONS_BASE);
    expect(req.request.method).toBe('POST');
    req.flush({ session_id: 'sid-001' });
  });

  it('returns an object with a session_id field', () => {
    let result: { session_id: string } | undefined;
    service.createSession().subscribe(r => (result = r));

    httpMock.expectOne(SESSIONS_BASE).flush({ session_id: 'sid-xyz' });
    expect(result?.session_id).toBe('sid-xyz');
  });
});

describe('EstimationService — createWithAttachments()', () => {
  let service: EstimationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(EstimationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('sends POST to /sessions/{id}/estimate', () => {
    const fd = new FormData();
    fd.append('transcript', 'Hello world');

    service.createWithAttachments('sid-001', fd).subscribe();

    const req = httpMock.expectOne(r => r.url === `${SESSIONS_BASE}/sid-001/estimate`);
    expect(req.request.method).toBe('POST');
    req.flush(MOCK_SESSION_RESPONSE);
  });

  it('sends the FormData body as-is', () => {
    const fd = new FormData();
    fd.append('transcript', 'My project description here');

    service.createWithAttachments('sid-002', fd).subscribe();

    const req = httpMock.expectOne(r => r.url.includes('/sid-002/estimate'));
    expect(req.request.body).toBe(fd);
    req.flush(MOCK_SESSION_RESPONSE);
  });

  it('defaults prompt_version query param to v1', () => {
    service.createWithAttachments('sid-003', new FormData()).subscribe();

    const req = httpMock.expectOne(r => r.url.includes('/sid-003/estimate'));
    expect(req.request.params.get('prompt_version')).toBe('v1');
    req.flush(MOCK_SESSION_RESPONSE);
  });

  it('uses the provided prompt_version query param', () => {
    service.createWithAttachments('sid-004', new FormData(), 'v2').subscribe();

    const req = httpMock.expectOne(r => r.url.includes('/sid-004/estimate'));
    expect(req.request.params.get('prompt_version')).toBe('v2');
    req.flush(MOCK_SESSION_RESPONSE);
  });

  it('returns the SessionEstimationResponse on success', () => {
    let result: SessionEstimationResponse | undefined;
    service.createWithAttachments('sid-005', new FormData()).subscribe(r => (result = r));

    httpMock.expectOne(r => r.url.includes('/sid-005/estimate')).flush(MOCK_SESSION_RESPONSE);

    expect(result?.model).toBe('gpt-4o-mini');
    expect(result?.input_tokens).toBe(320);
    expect(result?.estimation).toContain('Phase 1');
  });
});

describe('EstimationService — createWithAttachmentsStream()', () => {
  let service: EstimationService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(EstimationService);
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('includes the bearer token from localStorage in the streaming request', async () => {
    localStorage.setItem('access_token', 'stream.token');

    const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi
            .fn()
            .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('chunk-1') })
            .mockResolvedValueOnce({ done: true, value: undefined }),
        }),
      },
    } as unknown as Response);

    await new Promise<void>((resolve, reject) => {
      service.createWithAttachmentsStream('sid-stream', new FormData()).subscribe({
        complete: () => resolve(),
        error: reject,
      });
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0];
    const headers = init?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer stream.token');
  });

  it('omits Authorization when there is no stored token', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi
            .fn()
            .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('chunk-1') })
            .mockResolvedValueOnce({ done: true, value: undefined }),
        }),
      },
    } as unknown as Response);

    await new Promise<void>((resolve, reject) => {
      service.createWithAttachmentsStream('sid-stream', new FormData()).subscribe({
        complete: () => resolve(),
        error: reject,
      });
    });

    const [, init] = fetchSpy.mock.calls[0];
    const headers = init?.headers as Headers;
    expect(headers.has('Authorization')).toBe(false);
  });
});
