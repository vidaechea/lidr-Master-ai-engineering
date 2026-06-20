# RAG Pipeline Estimation Guide

Frontend implementation for Session 09 RAG pipeline with retrieval-augmented generation (RAG) for structured budget estimation.

---

## Overview

The RAG Pipeline feature enables users to submit budget transcripts and receive structured estimations using an advanced AI pipeline:

1. **Reformulation** — Extract keywords, sector, year range from transcript
2. **Retrieval** — Semantic search across budget corpus with metadata filtering
3. **Assembly** — Assemble context respecting token budget
4. **Generation** — LLM generates structured estimate with citations

---

## Components

### RagEstimationFormComponent

**Location:** `src/app/features/estimations/rag-estimation-form/`

**Purpose:** Collect user input for RAG pipeline estimation

**Features:**
- Transcript input with validation (20-50,000 characters)
- Advanced options:
  - `top_k` (1-50): Number of top-k retrieval results
  - `distance_threshold` (0.0-1.0): Semantic similarity threshold
  - `idempotency_key`: Optional cache key for duplicate requests
- Real-time character counter with status indicators
- Error handling with user-friendly messages
- Form reset functionality

**Template Elements:**
- Transcript textarea with dynamic validation
- Status indicator (empty/short/valid/long)
- Advanced options section with sliders
- Submit and reset buttons
- Info panel explaining the RAG pipeline

**Usage:**
```typescript
// Navigate to form
this.router.navigate(['/estimations/rag-form']);
```

### RagEstimationResultComponent

**Location:** `src/app/features/estimations/rag-estimation-result/`

**Purpose:** Display comprehensive RAG pipeline results

**Tabs:**
1. **Modules & Tasks** — Breakdown by engineering effort
   - Module-level effort in engineer days
   - Task-level breakdown with individual effort
   - Collapsible expansion panels

2. **Assumptions** — List of project assumptions
   - Automatically extracted from LLM generation
   - Displayed with checkmark icons

3. **Retrieved Chunks** — Semantic search results
   - Source ID and distance metrics
   - Chunk content with formatting
   - Metadata tags (sector, year, etc.)
   - Copy-to-clipboard for source IDs

4. **Pipeline Stages** — Technical details
   - Reformulation stage output (keywords, sector, year range)
   - Retrieval stage metadata
   - Assembly token count and truncation flag
   - Generation pipeline timing

**Summary Card:**
- Executive summary text
- High/Low confidence badge (colored)
- Metrics grid (total days, modules count, sources, candidates)

**Actions:**
- Export as JSON file
- Back to new estimation
- Copy source ID to clipboard

**Usage:**
```typescript
// Navigate with result data
this.router.navigate(['/estimations/rag-results'], {
  state: { result: ragResponse }
});
```

### RagEstimationService

**Location:** `src/app/features/estimations/rag-estimation.service.ts`

**Purpose:** HTTP proxy and utility methods for RAG pipeline

**API Methods:**

```typescript
// Create estimation (full orchestration)
createEstimation(request: RagEstimationRequest): Observable<FullRagEstimationResponse>

// Retrieve single estimation
getEstimation(estimationId: string): Observable<FullRagEstimationResponse>

// List estimations with filters
listEstimations(params?: {
  project_id?: string;
  status?: 'completed' | 'failed' | 'pending';
  limit?: number;
  offset?: number;
}): Observable<RagEstimationListItem[]>
```

**Utility Methods:**

```typescript
// Format engineer days (e.g., "5.0 days" or "4h")
formatEngineerDays(days: number): string

// Calculate total days across modules
calculateTotalDays(modules: RagEstimateModule[]): number

// Format confidence level
formatConfidence(lowConfidence: boolean): string

// Get CSS class for styling
getConfidenceClass(lowConfidence: boolean): string
```

---

## Data Models

### Request Model: RagEstimationRequest

```typescript
interface RagEstimationRequest {
  transcript: string;           // 20-50,000 characters
  top_k?: number;               // 1-50, default 5
  distance_threshold?: number;  // 0.0-1.0, default 0.35
  idempotency_key?: string;     // Optional cache key
}
```

### Response Model: FullRagEstimationResponse

```typescript
interface FullRagEstimationResponse {
  request_id: string | null;              // Request correlation ID
  reformulation: ReformulationStageOut;   // Extracted query info
  retrieval: { retrieval: RetrievalResult };  // Retrieved chunks
  assembly: AssemblyResult;               // Assembled context
  generation: { estimate: RagPipelineEstimate };  // Generated estimate
  idempotency_hit: boolean;               // Cached result flag
  processing_time_ms?: number;            // Pipeline duration
}
```

### Key Data Types

```typescript
// Generated estimation
interface RagPipelineEstimate {
  summary: string;                    // Executive summary
  low_confidence: boolean;            // Confidence flag
  modules: RagEstimateModule[];       // Work breakdown
  assumptions: string[];              // Project assumptions
  sources: string[];                  // Retrieved source IDs
}

// Module with tasks
interface RagEstimateModule {
  name: string;                       // Module name (e.g., "Analysis")
  engineer_days: number;              // Module-level effort
  tasks: RagEstimateTask[];          // Sub-tasks
}

// Individual task
interface RagEstimateTask {
  name: string;                       // Task name
  engineer_days: number;              // Task effort
}

// Retrieved chunk from corpus
interface RetrievedChunk {
  source_id: string;                  // Citation reference
  chunk_id: number;                   // Unique chunk ID
  document_id: number;                // Document ID
  chunk_type: string;                 // Type (e.g., "budget")
  content: string;                    // Chunk text
  distance: number;                   // Cosine distance (0-1)
  metadata: Record<string, any>;      // Custom metadata
}
```

---

## Routes

Add to `app.routes.ts`:

```typescript
{
  path: 'estimations',
  canActivate: [authGuard],
  children: [
    {
      path: 'rag-form',
      loadComponent: () =>
        import('./features/estimations/rag-estimation-form/rag-estimation-form.component')
          .then(m => m.RagEstimationFormComponent),
    },
    {
      path: 'rag-results',
      loadComponent: () =>
        import('./features/estimations/rag-estimation-result/rag-estimation-result.component')
          .then(m => m.RagEstimationResultComponent),
    },
  ],
}
```

---

## Workflow

### User Perspective

1. Navigate to `/estimations/rag-form`
2. Enter budget transcript (min 20 chars)
3. (Optional) Adjust advanced settings:
   - Top-K retrieval count
   - Distance threshold for semantic matching
   - Idempotency key for caching
4. Click "Generate Estimation"
5. Wait for backend processing (60-120 seconds typical)
6. View results at `/estimations/rag-results` with:
   - Executive summary
   - Module/task breakdown
   - Retrieved supporting chunks
   - Pipeline stage details

### Developer Integration

```typescript
// In a component
constructor(
  private ragService: RagEstimationService,
  private router: Router
) {}

// Create estimation
async submitEstimate() {
  try {
    const request: RagEstimationRequest = {
      transcript: userInput,
      top_k: 5,
      distance_threshold: 0.35,
    };

    const response = await this.ragService
      .createEstimation(request)
      .toPromise();

    // Navigate to results
    this.router.navigate(['/estimations/rag-results'], {
      state: { result: response }
    });
  } catch (error) {
    // Handle error
  }
}

// Retrieve results
async loadEstimation(id: string) {
  const result = await this.ragService
    .getEstimation(id)
    .toPromise();
  // Display result
}

// List estimations with filters
async loadList() {
  const items = await this.ragService
    .listEstimations({
      status: 'completed',
      limit: 20,
      offset: 0
    })
    .toPromise();
}
```

---

## Testing

### Unit Tests

Run RAG-related tests:

```bash
npm test -- rag-estimation
```

**Test Files:**
- `rag-estimation.service.spec.ts` — Service HTTP calls and utilities
- `rag-estimation-form.component.spec.ts` — Form validation and submission
- `rag-estimation-result.component.spec.ts` — Results display logic

**Coverage:**
- Form validation (min/max length, format)
- API integration (POST, GET requests)
- Data transformation (formatEngineerDays, calculateTotalDays)
- Navigation and error handling

### End-to-End Tests

Add Playwright tests in `tests/e2e/`:

```typescript
test('RAG estimation workflow', async ({ page }) => {
  // Navigate to form
  await page.goto('/estimations/rag-form');

  // Fill transcript
  await page.fill('textarea[formControlName="transcript"]', 'Sample...');

  // Submit
  await page.click('button[type="submit"]');

  // Wait for results
  await page.waitForURL('/estimations/rag-results');

  // Verify summary visible
  expect(page.locator('.summary-text')).toBeDefined();
});
```

---

## Styling

Components use Material Design with custom SCSS:

### Form Component (`rag-estimation-form.component.scss`)
- Grid layout with responsive breakpoints
- Gradient info panel
- Animated spinner on submit button
- Status indicator colors (empty/short/valid/long)

### Results Component (`rag-estimation-result.component.scss`)
- Multi-tab layout with icon labels
- Expandable panels for modules and chunks
- Confidence-based badge styling (high/low)
- Metrics grid responsive layout
- Code/monospace font for technical data

### Material Design Integration
- `MatCardModule` — Container cards
- `MatFormFieldModule` — Form inputs
- `MatTabsModule` — Tabbed results view
- `MatExpansionModule` — Collapsible panels
- `MatChipsModule` — Tags and badges
- `MatIconModule` — Material icons
- `MatProgressSpinnerModule` — Loading states
- `MatButtonModule` — Action buttons

---

## Error Handling

### HTTP Errors

Handled in `RagEstimationService`:
- **400 Bad Request** — Invalid input validation
- **404 Not Found** — Estimation not found
- **500 Server Error** — Backend processing failure
- **502 Bad Gateway** — AI engine unavailable
- **Network timeout** — Connection failure (120s timeout)

### User Feedback

Form component displays:
- Validation errors (character count, format)
- API error messages (detail text)
- Loading states with spinner
- Success navigation to results

---

## Performance Considerations

### Optimization

1. **Lazy Loading**
   - Components lazy-load via routes
   - Service methods use OnPush change detection

2. **HTTP Timeouts**
   - Estimation: 120 seconds
   - Retrieval-only: 60 seconds
   - Stage endpoints: 10-30 seconds

3. **Caching**
   - Idempotency key optional caching on backend
   - Same request returns 200 OK (idempotency_hit: true)

4. **Pagination**
   - List endpoint supports limit/offset
   - Typical page size: 20 items

---

## Common Issues

### "Minimum 20 characters required"
- Transcript is too short
- Minimum length: 20 characters
- Recommended: 100+ characters for better results

### "Distance threshold out of range"
- Value must be 0.0 to 1.0
- Default: 0.35 (recommended)
- Lower = stricter semantic matching

### "No results found"
- Corpus may not have relevant documents
- Check retrieval metadata filters (sector, year)
- Try different keywords

### "Low confidence estimate"
- Few or distant retrieved chunks
- Consider adjusting distance_threshold down
- Ensure transcript contains sufficient detail

---

## Deployment

### Environment Configuration

Update `environment.prod.ts`:

```typescript
export const environment = {
  production: true,
  apiUrl: 'https://api.example.com',
  ragPipelineTimeoutMs: 120000,
};
```

### Build

```bash
npm run build -- --configuration production
```

### Docker (Optional)

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 4200
CMD ["npm", "start"]
```

---

## Further Reading

- [Backend RAG Pipeline Documentation](../../ai-engine/README.md)
- [Angular Material Components](https://material.angular.io)
- [RxJS Documentation](https://rxjs.dev)
- [FastAPI Backend API Spec](../../application-web/backend/README.md)
