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
