import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSliderModule } from '@angular/material/slider';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';

import { RagEstimationService } from '../rag-estimation.service';

@Component({
  selector: 'app-rag-estimation-form',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatSliderModule,
    MatChipsModule,
    MatIconModule,
  ],
  templateUrl: './rag-estimation-form.component.html',
  styleUrls: ['./rag-estimation-form.component.scss'],
})
export class RagEstimationFormComponent implements OnInit {
  form!: FormGroup;
  isLoading = signal(false);
  error = signal<string | null>(null);
  characterCount = signal(0);
  minCharacters = 20;
  maxCharacters = 50000;

  constructor(
    private fb: FormBuilder,
    private ragEstimationService: RagEstimationService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.initializeForm();
  }

  private initializeForm(): void {
    this.form = this.fb.group({
      transcript: [
        '',
        [
          Validators.required,
          Validators.minLength(this.minCharacters),
          Validators.maxLength(this.maxCharacters),
        ],
      ],
      top_k: [5, [Validators.min(1), Validators.max(50)]],
      distance_threshold: [0.35, [Validators.min(0.0), Validators.max(1.0)]],
      idempotency_key: [''],
    });

    // Track character count
    this.form.get('transcript')?.valueChanges.subscribe((value) => {
      this.characterCount.set(value?.length || 0);
    });
  }

  getTranscriptStatus(): {
    status: 'empty' | 'short' | 'valid' | 'long';
    message: string;
  } {
    const count = this.characterCount();

    if (count === 0) {
      return { status: 'empty', message: 'Enter transcript...' };
    }
    if (count < this.minCharacters) {
      return {
        status: 'short',
        message: `${this.minCharacters - count} characters remaining`,
      };
    }
    if (count >= this.maxCharacters) {
      return {
        status: 'long',
        message: `${count - this.maxCharacters} characters over limit`,
      };
    }
    return {
      status: 'valid',
      message: `${this.maxCharacters - count} characters available`,
    };
  }

  canSubmit(): boolean {
    return this.form.valid && !this.isLoading();
  }

  async onSubmit(): Promise<void> {
    if (!this.form.valid) {
      this.error.set('Please fix validation errors');
      return;
    }

    this.isLoading.set(true);
    this.error.set(null);

    try {
      const request = {
        transcript: this.form.value.transcript.trim(),
        top_k: this.form.value.top_k,
        distance_threshold: this.form.value.distance_threshold,
        idempotency_key: this.form.value.idempotency_key || undefined,
      };

      const response = await this.ragEstimationService.createEstimation(request).toPromise();

      if (response) {
        // Navigate to results page with response data
        await this.router.navigate(['/estimations/rag-results'], {
          state: { result: response },
        });
      }
    } catch (err: any) {
      const message = err?.error?.detail || err?.message || 'Estimation failed';
      this.error.set(message);
      console.error('RAG estimation error:', err);
    } finally {
      this.isLoading.set(false);
    }
  }

  onReset(): void {
    this.form.reset({
      transcript: '',
      top_k: 5,
      distance_threshold: 0.35,
      idempotency_key: '',
    });
    this.characterCount.set(0);
    this.error.set(null);
  }

  get transcript() {
    return this.form.get('transcript');
  }

  get top_k() {
    return this.form.get('top_k');
  }

  get distance_threshold() {
    return this.form.get('distance_threshold');
  }
}
