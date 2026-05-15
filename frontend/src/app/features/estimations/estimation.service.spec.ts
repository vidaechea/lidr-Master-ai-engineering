import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { EstimationService, EstimationCreate, EstimationOut } from './estimation.service';
import { environment } from '../../../environments/environment';

const BASE = `${environment.apiUrl}/v1/estimations`;

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
});
