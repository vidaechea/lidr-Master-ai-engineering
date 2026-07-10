import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';

import { RagEstimationService } from './rag-estimation.service';
import { environment } from '../../../environments/environment';

describe('RagEstimationService', () => {
  let service: RagEstimationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [RagEstimationService],
    });

    service = TestBed.inject(RagEstimationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('createEstimation', () => {
    it('should POST to /v1/rag/estimate', () => {
      const request = {
        transcript: 'Sample budget transcript',
        top_k: 5,
        distance_threshold: 0.35,
      };

      service.createEstimation(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/estimate`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('getEstimation', () => {
    it('should GET /v1/rag/estimates/{id}', () => {
      const estimationId = '123-456';

      service.getEstimation(estimationId).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/estimates/${estimationId}`);
      expect(req.request.method).toBe('GET');
    });
  });

  describe('verifyStage', () => {
    it('should POST to /v1/rag/stages/verify', () => {
      const request = {
        estimate: {
          summary: 'Estimate',
          estimate_markdown: null,
          low_confidence: false,
          modules: [],
          line_items: [],
          assumptions: [],
          sources: [],
        },
        kept_chunks: [],
        use_judge: true,
      };

      service.verifyStage(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/stages/verify`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('estimateTaskHours', () => {
    it('should POST to /v1/rag/tasks/hours', () => {
      const request = {
        modules: [
          {
            name: 'Billing',
            tasks: [{ name: 'Implement checkout' }],
          },
        ],
      };

      service.estimateTaskHours(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/tasks/hours`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('proposeAgentStructure', () => {
    it('should POST to /v1/rag/agent/structure', () => {
      const request = {
        query: {
          search_text: 'Need a backend and mobile budget',
          chunk_types: ['budget_component'],
          keywords: ['backend'],
        },
        profile_id: '11111111-1111-1111-1111-111111111111',
      };

      service.proposeAgentStructure(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/structure`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('estimateAgentHours', () => {
    it('should POST to /v1/rag/agent/hours', () => {
      const request = {
        modules: [
          {
            name: 'Authentication',
            tasks: [{ name: 'Implement OAuth backend' }],
          },
        ],
        profile_id: '11111111-1111-1111-1111-111111111111',
      };

      service.estimateAgentHours(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/hours`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('agent profile CRUD', () => {
    it('should GET /v1/rag/agent/profiles', () => {
      service.listAgentProfiles().subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/profiles`);
      expect(req.request.method).toBe('GET');
    });

    it('should POST /v1/rag/agent/profiles', () => {
      const request = {
        name: 'Conservative',
        persona: 'Prefer lower-risk estimates',
        config: { reasoning_effort: 'low' as const },
        is_default: true,
      };

      service.createAgentProfile(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/profiles`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });

    it('should PATCH /v1/rag/agent/profiles/{id}', () => {
      const profileId = '22222222-2222-2222-2222-222222222222';
      const request = { name: 'Updated' };

      service.updateAgentProfile(profileId, request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/profiles/${profileId}`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual(request);
    });

    it('should DELETE /v1/rag/agent/profiles/{id}', () => {
      const profileId = '33333333-3333-3333-3333-333333333333';

      service.deleteAgentProfile(profileId).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/agent/profiles/${profileId}`);
      expect(req.request.method).toBe('DELETE');
    });
  });

  describe('createIndexRun', () => {
    it('should POST to /v1/rag/index/runs', () => {
      const request = {
        documents: [{ budget_id: 'B1' }],
        document_type: 'historical_budget',
        chunk_type: 'budget_component',
      };

      service.createIndexRun(request).subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/index/runs`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(request);
    });
  });

  describe('getIndexJob', () => {
    it('should GET /v1/rag/index/jobs/{id}', () => {
      service.getIndexJob('job-1').subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/index/jobs/job-1`);
      expect(req.request.method).toBe('GET');
    });
  });

  describe('getIndexStats', () => {
    it('should GET /v1/rag/index/stats', () => {
      service.getIndexStats().subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/v1/rag/index/stats`);
      expect(req.request.method).toBe('GET');
    });
  });

  describe('listEstimations', () => {
    it('should GET /v1/rag/estimates with filters', () => {
      const params = {
        status: 'completed' as const,
        limit: 10,
        offset: 0,
      };

      service.listEstimations(params).subscribe();

      const req = httpMock.expectOne((request) =>
        request.url === `${environment.apiUrl}/v1/rag/estimates` &&
        request.params.get('status') === 'completed' &&
        request.params.get('limit') === '10'
      );
      expect(req.request.method).toBe('GET');
    });
  });

  describe('calculateTotalDays', () => {
    it('should sum engineer days across modules and tasks', () => {
      const modules = [
        {
          name: 'Module 1',
          engineer_days: 5,
          tasks: [
            { name: 'Task 1', engineer_days: 3 },
            { name: 'Task 2', engineer_days: 2 },
          ],
        },
        {
          name: 'Module 2',
          engineer_days: 2,
          tasks: [{ name: 'Task 3', engineer_days: 1 }],
        },
      ];

      const total = service.calculateTotalDays(modules);

      expect(total).toBe(13); // 5+3+2+2+1
    });
  });

  describe('formatEngineerDays', () => {
    it('should format less than 1 day as hours', () => {
      expect(service.formatEngineerDays(0.5)).toBe('4h');
      expect(service.formatEngineerDays(0.125)).toBe('1h');
    });

    it('should format 1 or more days', () => {
      expect(service.formatEngineerDays(1.0)).toBe('1.0 days');
      expect(service.formatEngineerDays(5.5)).toBe('5.5 days');
    });
  });

  describe('formatConfidence', () => {
    it('should return "High" for high confidence', () => {
      expect(service.formatConfidence(false)).toBe('High');
    });

    it('should return "Low" for low confidence', () => {
      expect(service.formatConfidence(true)).toBe('Low');
    });
  });

  describe('getConfidenceClass', () => {
    it('should return correct CSS class', () => {
      expect(service.getConfidenceClass(false)).toBe('confidence-high');
      expect(service.getConfidenceClass(true)).toBe('confidence-low');
    });
  });
});
