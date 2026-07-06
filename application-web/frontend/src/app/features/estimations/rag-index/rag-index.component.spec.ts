import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { RagIndexComponent } from './rag-index.component';
import { RagEstimationService } from '../rag-estimation.service';

describe('RagIndexComponent', () => {
  let component: RagIndexComponent;
  let fixture: ComponentFixture<RagIndexComponent>;
  let ragService: {
    getIndexStats: ReturnType<typeof vi.fn>;
    createIndexRun: ReturnType<typeof vi.fn>;
    getIndexJob: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    const ragServiceSpy = {
      getIndexStats: vi.fn().mockReturnValue(
        of({
          collections: [{ collection: 'budget', documents: 1, chunks: 2, hnsw_indexed: false }],
          total_chunks: 2,
        })
      ),
      createIndexRun: vi.fn().mockReturnValue(of({ job_id: 'job-1', documents_total: 1, status: 'pending' })),
      getIndexJob: vi
        .fn()
        .mockReturnValueOnce(of({
          job_id: 'job-1',
          status: 'running',
          documents_processed: 0,
          error_message: null,
          started_at: '2026-07-06T11:00:00Z',
          finished_at: null,
        }))
        .mockReturnValueOnce(of({
          job_id: 'job-1',
          status: 'completed',
          documents_processed: 1,
          error_message: null,
          started_at: '2026-07-06T11:00:00Z',
          finished_at: '2026-07-06T11:00:05Z',
        })),
    };

    await TestBed.configureTestingModule({
      imports: [RagIndexComponent],
      providers: [{ provide: RagEstimationService, useValue: ragServiceSpy }],
    }).compileComponents();

    ragService = TestBed.inject(RagEstimationService) as unknown as {
      getIndexStats: ReturnType<typeof vi.fn>;
      createIndexRun: ReturnType<typeof vi.fn>;
      getIndexJob: ReturnType<typeof vi.fn>;
    };

    fixture = TestBed.createComponent(RagIndexComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load index stats on init', () => {
    expect(ragService.getIndexStats).toHaveBeenCalledTimes(1);
    expect(component.indexCollections().length).toBe(1);
    expect(component.indexCollections()[0].collection).toBe('budget');
  });

  it('should start index run and poll until completion', async () => {
    component.startSampleIndexRun();

    expect(ragService.createIndexRun).toHaveBeenCalledTimes(1);
    expect(ragService.getIndexJob).toHaveBeenCalledTimes(1);

    await new Promise(resolve => setTimeout(resolve, 1600));

    expect(ragService.getIndexJob).toHaveBeenCalledTimes(2);
    expect(component.indexJob()?.status).toBe('completed');
  });
});
