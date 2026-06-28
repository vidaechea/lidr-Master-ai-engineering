import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { vi } from 'vitest';

import { RagEstimationResultComponent } from './rag-estimation-result.component';
import { RagEstimateModule, RagEstimationService } from '../rag-estimation.service';

describe('RagEstimationResultComponent', () => {
  let component: RagEstimationResultComponent;
  let fixture: ComponentFixture<RagEstimationResultComponent>;
  let router: { navigate: ReturnType<typeof vi.fn>; currentNavigation: ReturnType<typeof vi.fn> };
  let ragService: {
    formatEngineerDays: ReturnType<typeof vi.fn>;
    calculateTotalDays: ReturnType<typeof vi.fn>;
  };

  const mockResult = {
    request_id: 'req-123',
    processing_time_ms: 1500,
    idempotency_hit: false,
    reformulation: {
      search_text: 'budget estimation',
      sector: 'fintech',
      year_from: 2023,
      year_to: 2025,
      chunk_types: ['budget', 'timeline'],
      keywords: ['blockchain', 'payment'],
      used_fallback: false,
    },
    retrieval: {
      retrieval: {
        query: 'budget estimation',
        top_k: 5,
        candidates_evaluated: 100,
        low_confidence: false,
        chunks: [
          {
            source_id: 'src-1',
            chunk_id: 1,
            document_id: 101,
            chunk_type: 'budget',
            content: 'Test chunk content',
            distance: 0.15,
            metadata: { client_sector: 'fintech', year: 2023 },
          },
        ],
      },
    },
    assembly: {
      context_block: 'Assembled context...',
      included_source_ids: ['src-1'],
      token_count_estimate: 500,
      truncated: false,
    },
    generation: {
      estimate: {
        summary: 'Estimated 20 engineer days',
        low_confidence: false,
        modules: [
          {
            name: 'Analysis',
            engineer_days: 5,
            tasks: [
              { name: 'Requirements', engineer_days: 3 },
              { name: 'Design', engineer_days: 2 },
            ],
          },
          {
            name: 'Implementation',
            engineer_days: 10,
            tasks: [{ name: 'Coding', engineer_days: 10 }],
          },
        ],
        assumptions: ['Team has blockchain experience'],
        sources: ['src-1'],
      },
    },
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(async () => {
    const routerSpy = {
      navigate: vi.fn().mockResolvedValue(true),
      currentNavigation: vi.fn().mockReturnValue(null),
    };
    const ragServiceSpy = {
      formatEngineerDays: vi.fn((days: number) => {
        return days < 1 ? `${Math.round(days * 8)}h` : `${days.toFixed(1)} days`;
      }),
      calculateTotalDays: vi.fn((modules: RagEstimateModule[]) => {
        return modules.reduce(
          (total: number, m: RagEstimateModule) =>
            total +
            m.engineer_days +
            m.tasks.reduce((sum: number, t) => sum + t.engineer_days, 0),
          0
        );
      }),
    };

    ragServiceSpy.formatEngineerDays.mockImplementation((days: number) => {
      return days < 1 ? `${Math.round(days * 8)}h` : `${days.toFixed(1)} days`;
    });

    await TestBed.configureTestingModule({
      imports: [RagEstimationResultComponent, NoopAnimationsModule],
      providers: [
        { provide: Router, useValue: routerSpy },
        { provide: RagEstimationService, useValue: ragServiceSpy },
      ],
    }).compileComponents();

    router = TestBed.inject(Router) as unknown as {
      navigate: ReturnType<typeof vi.fn>;
      currentNavigation: ReturnType<typeof vi.fn>;
    };
    ragService = TestBed.inject(RagEstimationService) as unknown as {
      formatEngineerDays: ReturnType<typeof vi.fn>;
      calculateTotalDays: ReturnType<typeof vi.fn>;
    };

    fixture = TestBed.createComponent(RagEstimationResultComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Initialization', () => {
    it('should load result from router state', () => {
      component.result.set(mockResult as any);
      expect(component.result()).toBeTruthy();
    });

    it('should set error if no result found', () => {
      component.ngOnInit();
      expect(component.error()).toContain('No estimation result found');
    });
  });

  describe('Total Engineer Days Computation', () => {
    it('should calculate total days across all modules', () => {
      component.result.set(mockResult as any);

      const total = component.totalEngineerDays();

      expect(total).toBe(30); // 5 + 3 + 2 + 10 + 10
    });

    it('should return 0 if no result', () => {
      expect(component.totalEngineerDays()).toBe(0);
    });
  });

  describe('Module Calculations', () => {
    it('should calculate module days including tasks', () => {
      const module = mockResult.generation.estimate.modules[0];
      const total = component.calculateModuleDays(module);

      expect(total).toBe(10); // 5 + 3 + 2
    });
  });

  describe('Confidence Styling', () => {
    it('should return high confidence class', () => {
      component.result.set(mockResult as any);
      expect(component.confidenceClass()).toBe('confidence-high');
    });

    it('should return low confidence class', () => {
      const lowConfResult = { ...mockResult };
      lowConfResult.generation.estimate.low_confidence = true;
      component.result.set(lowConfResult as any);

      expect(component.confidenceClass()).toBe('confidence-low');
    });
  });

  describe('Confidence Percentage', () => {
    it('should calculate confidence percentage', () => {
      component.result.set(mockResult as any);
      const percentage = component.getConfidencePercentage();

      expect(percentage).toBe(1); // 1 chunk / 100 candidates
    });

    it('should return 0 if no chunks', () => {
      const noChunkResult = { ...mockResult };
      noChunkResult.retrieval.retrieval.chunks = [];
      component.result.set(noChunkResult as any);

      expect(component.getConfidencePercentage()).toBe(0);
    });
  });

  describe('Distance Formatting', () => {
    it('should format distance as percentage', () => {
      expect(component.formatDistance(0.15)).toBe('15.0%');
      expect(component.formatDistance(0.5)).toBe('50.0%');
    });
  });

  describe('Navigation', () => {
    it('should navigate back to estimations', () => {
      component.goBack();
      expect(router.navigate).toHaveBeenCalledWith(['/estimations']);
    });
  });

  describe('Export', () => {
    it('should export result as JSON file', () => {
      component.result.set(mockResult as any);

      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
      const linkSpy = vi.spyOn(document, 'createElement').mockReturnValue({
        click: vi.fn(),
        href: '',
        download: '',
      } as any);

      component.exportAsJSON();

      expect(linkSpy).toHaveBeenCalledWith('a');
      expect(URL.revokeObjectURL).toHaveBeenCalled();
    });
  });

  describe('Clipboard Copy', () => {
    it('should copy source ID to clipboard', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText },
        configurable: true,
      });

      await component.copySourceIdToClipboard('src-123');

      expect(writeText).toHaveBeenCalledWith('src-123');
    });
  });
});
