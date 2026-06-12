import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { ProjectService, Project, ProjectCreate } from './project.service';
import { environment } from '../../../environments/environment';

const BASE = `${environment.apiUrl}/v1/projects`;

const MOCK_PROJECT: Project = {
  id: 'proj-001',
  name: 'Admin Portal',
  description: 'B2B SaaS admin panel',
  project_type: 'web_saas',
  created_at: '2026-05-15T10:00:00Z',
  updated_at: '2026-05-15T10:00:00Z',
};

describe('ProjectService', () => {
  let service: ProjectService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProjectService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  // ── load() ────────────────────────────────────────────────────────────────

  describe('load()', () => {
    it('sends GET /v1/projects', () => {
      service.load().subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.method).toBe('GET');
      req.flush([MOCK_PROJECT]);
    });

    it('updates the projects signal with the response array', () => {
      service.load().subscribe();
      httpMock.expectOne(BASE).flush([MOCK_PROJECT]);

      expect(service.projects()).toEqual([MOCK_PROJECT]);
    });

    it('sets projects signal to empty array when response is empty', () => {
      service.load().subscribe();
      httpMock.expectOne(BASE).flush([]);

      expect(service.projects()).toEqual([]);
    });

    it('does not send query params', () => {
      service.load().subscribe();
      const req = httpMock.expectOne(BASE);
      expect(req.request.params.keys().length).toBe(0);
      req.flush([]);
    });
  });

  // ── create() ──────────────────────────────────────────────────────────────

  describe('create()', () => {
    it('sends POST /v1/projects with the full project payload', () => {
      const data: ProjectCreate = {
        name: 'New Project',
        description: 'A new project',
        project_type: 'web_saas',
      };

      service.create(data).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(data);
      req.flush(MOCK_PROJECT);
    });

    it('sends POST with only name when optional fields are omitted', () => {
      service.create({ name: 'Minimal' }).subscribe();

      const req = httpMock.expectOne(BASE);
      expect(req.request.body).toEqual({ name: 'Minimal' });
      req.flush(MOCK_PROJECT);
    });
  });

  // ── update() ──────────────────────────────────────────────────────────────

  describe('update()', () => {
    it('sends PATCH /v1/projects/{id} with the update payload', () => {
      service.update('proj-001', { name: 'Renamed Project' }).subscribe();

      const req = httpMock.expectOne(`${BASE}/proj-001`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ name: 'Renamed Project' });
      req.flush({ ...MOCK_PROJECT, name: 'Renamed Project' });
    });

    it('sends PATCH with only the changed fields', () => {
      service.update('proj-001', { description: 'New desc' }).subscribe();

      const req = httpMock.expectOne(`${BASE}/proj-001`);
      expect(req.request.body).toEqual({ description: 'New desc' });
      req.flush(MOCK_PROJECT);
    });
  });

  // ── delete() ──────────────────────────────────────────────────────────────

  describe('delete()', () => {
    it('sends DELETE /v1/projects/{id}', () => {
      service.delete('proj-001').subscribe();

      const req = httpMock.expectOne(`${BASE}/proj-001`);
      expect(req.request.method).toBe('DELETE');
      req.flush(null, { status: 204, statusText: 'No Content' });
    });
  });
});
