import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { RagEstimationFormComponent } from './rag-estimation-form.component';
import { RagEstimationService } from '../rag-estimation.service';

describe('RagEstimationFormComponent', () => {
  let component: RagEstimationFormComponent;
  let fixture: ComponentFixture<RagEstimationFormComponent>;
  let ragService: { createEstimation: ReturnType<typeof vi.fn> };
  let router: { navigate: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    const ragServiceSpy = {
      createEstimation: vi.fn(),
    };
    const routerSpy = {
      navigate: vi.fn().mockResolvedValue(true),
    };

    await TestBed.configureTestingModule({
      imports: [
        RagEstimationFormComponent,
        ReactiveFormsModule,
        NoopAnimationsModule,
      ],
      providers: [
        { provide: RagEstimationService, useValue: ragServiceSpy },
        { provide: Router, useValue: routerSpy },
      ],
    }).compileComponents();

    ragService = TestBed.inject(RagEstimationService) as unknown as {
      createEstimation: ReturnType<typeof vi.fn>;
    };
    router = TestBed.inject(Router) as unknown as {
      navigate: ReturnType<typeof vi.fn>;
    };

    fixture = TestBed.createComponent(RagEstimationFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('Form Initialization', () => {
    it('should initialize form with default values', () => {
      expect(component.form.get('transcript')?.value).toBe('');
      expect(component.form.get('top_k')?.value).toBe(5);
      expect(component.form.get('distance_threshold')?.value).toBe(0.35);
      expect(component.form.get('idempotency_key')?.value).toBe('');
    });

    it('should have validators on transcript field', () => {
      const control = component.form.get('transcript');
      expect(control?.hasError('required')).toBe(true);

      control?.setValue('short');
      expect(control?.hasError('minlength')).toBe(true);

      control?.setValue('a'.repeat(50001));
      expect(control?.hasError('maxlength')).toBe(true);
    });

    it('should track character count', () => {
      const control = component.form.get('transcript');
      control?.setValue('Hello World');

      expect(component.characterCount()).toBe(11);
    });
  });

  describe('Form Validation', () => {
    it('should disable submit when form is invalid', () => {
      component.form.get('transcript')?.setValue('');
      expect(component.canSubmit()).toBe(false);
    });

    it('should enable submit when form is valid', () => {
      component.form.get('transcript')?.setValue('a'.repeat(50));
      expect(component.canSubmit()).toBe(true);
    });

    it('should disable submit while loading', () => {
      component.form.get('transcript')?.setValue('a'.repeat(50));
      component.isLoading.set(true);
      expect(component.canSubmit()).toBe(false);
    });
  });

  describe('Transcript Status', () => {
    it('should return empty status for no input', () => {
      const status = component.getTranscriptStatus();
      expect(status.status).toBe('empty');
    });

    it('should return short status for insufficient characters', () => {
      component.characterCount.set(10);
      const status = component.getTranscriptStatus();
      expect(status.status).toBe('short');
    });

    it('should return valid status for acceptable length', () => {
      component.characterCount.set(100);
      const status = component.getTranscriptStatus();
      expect(status.status).toBe('valid');
    });

    it('should return long status for exceeding max', () => {
      component.characterCount.set(50001);
      const status = component.getTranscriptStatus();
      expect(status.status).toBe('long');
    });
  });

  describe('Form Submission', () => {
    it('should call createEstimation with valid request', async () => {
      const mockResponse = {
        request_id: '123',
        reformulation: {} as any,
        retrieval: {} as any,
        assembly: {} as any,
        generation: {} as any,
        idempotency_hit: false,
      };

      ragService.createEstimation.mockReturnValue(of(mockResponse));

      component.form.patchValue({
        transcript: 'a'.repeat(50),
        top_k: 10,
        distance_threshold: 0.25,
        idempotency_key: 'test-123',
      });

      await component.onSubmit();

      expect(ragService.createEstimation).toHaveBeenCalledWith({
        transcript: 'a'.repeat(50),
        top_k: 10,
        distance_threshold: 0.25,
        idempotency_key: 'test-123',
      });

      expect(router.navigate).toHaveBeenCalledWith(
        ['/estimations/rag-results'],
        expect.objectContaining({ state: { result: mockResponse } })
      );
    });

    it('should not submit if form is invalid', async () => {
      component.form.get('transcript')?.setValue('');
      await component.onSubmit();

      expect(ragService.createEstimation).not.toHaveBeenCalled();
      expect(component.error()).toContain('validation errors');
    });

    it('should handle API errors', async () => {
      const errorResponse = { error: { detail: 'API error' } };
      ragService.createEstimation.mockReturnValue(
        throwError(() => errorResponse)
      );

      component.form.patchValue({
        transcript: 'a'.repeat(50),
      });

      await component.onSubmit();

      expect(component.error()).toBe('API error');
      expect(component.isLoading()).toBe(false);
    });

    it('should trim whitespace from transcript', async () => {
      const mockResponse = {
        request_id: '123',
        reformulation: {} as any,
        retrieval: {} as any,
        assembly: {} as any,
        generation: {} as any,
        idempotency_hit: false,
      };

      ragService.createEstimation.mockReturnValue(of(mockResponse));

      component.form.patchValue({
        transcript: '  test transcript with enough length  ',
      });

      await component.onSubmit();

      expect(ragService.createEstimation).toHaveBeenCalledWith(
        expect.objectContaining({
          transcript: 'test transcript with enough length',
        })
      );
    });
  });

  describe('Form Reset', () => {
    it('should reset form to initial state', () => {
      component.form.patchValue({
        transcript: 'test',
        top_k: 10,
        distance_threshold: 0.5,
      });

      component.onReset();

      expect(component.form.get('transcript')?.value).toBe('');
      expect(component.form.get('top_k')?.value).toBe(5);
      expect(component.form.get('distance_threshold')?.value).toBe(0.35);
      expect(component.characterCount()).toBe(0);
      expect(component.error()).toBeNull();
    });
  });
});

