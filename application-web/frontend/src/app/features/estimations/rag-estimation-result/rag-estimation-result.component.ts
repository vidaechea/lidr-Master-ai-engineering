import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatChipsModule } from '@angular/material/chips';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { marked } from 'marked';

import {
  FullRagEstimationResponse,
  RagEstimateModule,
  RagEstimationService,
} from '../rag-estimation.service';

@Component({
  selector: 'app-rag-estimation-result',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatTabsModule,
    MatChipsModule,
    MatExpansionModule,
    MatProgressBarModule,
  ],
  templateUrl: './rag-estimation-result.component.html',
  styleUrls: ['./rag-estimation-result.component.scss'],
})
export class RagEstimationResultComponent implements OnInit {
  readonly result = signal<FullRagEstimationResponse | null>(null);
  readonly error = signal<string | null>(null);
  readonly selectedTabIndex = signal(0);

  readonly totalEngineerDays = computed(() => {
    const estimate = this.result()?.generation?.estimate;
    return estimate ? this.ragEstimationService.calculateTotalDays(estimate.modules) : 0;
  });

  readonly confidenceClass = computed(() => {
    return this.result()?.generation?.estimate?.low_confidence
      ? 'confidence-low'
      : 'confidence-high';
  });

  constructor(
    private readonly router: Router,
    private readonly ragEstimationService: RagEstimationService
  ) {}

  ngOnInit(): void {
    const state = this.router.currentNavigation()?.extras.state || history.state;

    if (state?.result) {
      this.result.set(state.result);
    } else {
      this.error.set('No estimation result found');
    }
  }

  formatEngineerDays(days: number): string {
    return this.ragEstimationService.formatEngineerDays(days);
  }

  calculateModuleDays(module: RagEstimateModule): number {
    return (
      module.engineer_days +
      module.tasks.reduce((sum, task) => sum + task.engineer_days, 0)
    );
  }

  getConfidencePercentage(): number {
    if (!this.result()?.retrieval?.retrieval?.chunks) return 0;
    const totalCandidates = this.result()?.retrieval?.retrieval?.candidates_evaluated || 1;
    const retrieved = this.result()?.retrieval?.retrieval?.chunks?.length || 0;
    return Math.round((retrieved / totalCandidates) * 100);
  }

  formatDistance(distance: number): string {
    return (distance * 100).toFixed(1) + '%';
  }

  renderMarkdown(markdown: string | null | undefined): string {
    if (!markdown) return '';
    return marked.parse(markdown, { async: false });
  }

  goBack(): void {
    this.router.navigate(['/estimations']);
  }

  exportAsJSON(): void {
    if (!this.result()) return;

    const dataStr = JSON.stringify(this.result(), null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `rag-estimation-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  copySourceIdToClipboard(sourceId: string): void {
    navigator.clipboard.writeText(sourceId);
  }
}
