import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { Observable } from 'rxjs';
import { vi } from 'vitest';

import { EstimationFormComponent } from './estimation-form.component';
import { EstimationService } from '../estimation.service';
import { environment } from '../../../../environments/environment';

const SESSIONS_BASE = `${environment.apiUrl}/v1/estimations/sessions`;

// ---------------------------------------------------------------------------
// Outer-scope helpers shared across suites
// ---------------------------------------------------------------------------

function makeFile(name: string, type: string, size = 1024): File {
  return new File(['x'.repeat(size)], name, { type });
}

function makeFileList(...files: File[]): FileList {
  const list = files.slice() as unknown as FileList;
  Object.defineProperty(list, 'item', {
    value: (index: number) => files[index] ?? null,
    configurable: true,
  });
  return list;
}

function setRequiredSubmitFields(component: EstimationFormComponent): void {
  component.form.transcription = VALID_TRANSCRIPTION;
  component.form.detail_level = 'detailed';
}

function setupWithAttachment() {
  const ctx = setup();
  setRequiredSubmitFields(ctx.component);
  const file = new File(['%PDF-1.4 fake'], 'spec.pdf', { type: 'application/pdf' });
  const input = document.createElement('input');
  Object.defineProperty(input, 'files', { value: makeFileList(file) });
  ctx.component.onFilesSelected({ target: input } as unknown as Event);
  return ctx;
}

const VALID_TRANSCRIPTION =
  'A B2B SaaS company needs an admin portal to manage their existing customer accounts.';

function setup() {
  TestBed.configureTestingModule({
    imports: [EstimationFormComponent],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([{ path: '**', redirectTo: '' }]),
      provideAnimationsAsync(),
    ],
  });

  const fixture = TestBed.createComponent(EstimationFormComponent);
  const component = fixture.componentInstance;
  const httpMock = TestBed.inject(HttpTestingController);
  const estimationService = TestBed.inject(EstimationService);
  fixture.detectChanges();

  httpMock.expectOne(SESSIONS_BASE).flush({ session_id: 'sid-bootstrap' });
  httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
    session_id: 'sid-bootstrap',
    project_metadata: {
      project_name: null,
      assumed_team_size: null,
      mentioned_technologies: [],
      agreed_scope: null,
    },
    history: [],
    turn_count: 0,
  });

  return { fixture, component, httpMock, estimationService };
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — initial state', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('creates successfully', () => {
    const { component } = setup();
    expect(component).toBeTruthy();
  });

  it('starts with loading=false', () => {
    const { component } = setup();
    expect(component.loading()).toBe(false);
  });

  it('starts with no error', () => {
    const { component } = setup();
    expect(component.error()).toBeNull();
  });

  it('starts with no guardrail error', () => {
    const { component } = setup();
    expect(component.guardrailError()).toBeNull();
  });

  it('cleans form state when starting a new conversation', () => {
    const { component, httpMock } = setup();

    setRequiredSubmitFields(component);
    component.form.project_type = 'web_saas';
    component.form.detail_level = 'detailed';
    component.form.temperature = 0.8;
    component.addRefProject();
    component.refProjects[0].name = 'Legacy project';
    component.activeTab.set('response');
    const input = document.createElement('input');
    Object.defineProperty(input, 'files', { value: makeFileList(makeFile('spec.pdf', 'application/pdf')) });
    component.onFilesSelected({ target: input } as unknown as Event);

    component.startNewConversation();

    expect(component.form.transcription).toBe('');
    expect(component.form.project_type).toBeUndefined();
    expect(component.form.detail_level).toBeUndefined();
    expect(component.form.temperature).toBeUndefined();
    expect(component.refProjects.length).toBe(0);
    expect(component.attachments()).toEqual([]);
    expect(component.activeTab()).toBe('form');

    httpMock.expectOne(SESSIONS_BASE).flush({ session_id: 'sid-new' });
    httpMock.expectOne(`${SESSIONS_BASE}/sid-new`).flush({
      session_id: 'sid-new',
      project_metadata: {
        project_name: null,
        assumed_team_size: null,
        mentioned_technologies: [],
        agreed_scope: null,
      },
      history: [],
      turn_count: 0,
    });
  });
});

// ---------------------------------------------------------------------------
// guardrailIcon()
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — guardrailIcon()', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('returns person_off for pii', () => {
    const { component } = setup();
    expect(component.guardrailIcon('pii')).toBe('person_off');
  });

  it('returns security for prompt_injection', () => {
    const { component } = setup();
    expect(component.guardrailIcon('prompt_injection')).toBe('security');
  });

  it('returns block for moderation', () => {
    const { component } = setup();
    expect(component.guardrailIcon('moderation')).toBe('block');
  });
});

// ---------------------------------------------------------------------------
// submit() — success path
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — submit() success', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('clears errors before submitting', () => {
    const { component, estimationService } = setup();
    component.error.set('previous error');
    component.guardrailError.set({ message: 'old', reason: 'pii' });
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));

    setRequiredSubmitFields(component);
    component.submit();

    expect(component.error()).toBeNull();
    expect(component.guardrailError()).toBeNull();
  });

  it('sets loading=true while request is in-flight', () => {
    const { component, estimationService } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.submit();

    expect(component.loading()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// submit() — guardrail error paths
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — submit() guardrail errors', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('sets guardrailError signal on 422 with reason=pii', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 422, detail: { message: 'Email address detected.', reason: 'pii' } })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    expect(component.guardrailError()).toEqual({
      message: 'Email address detected.',
      reason: 'pii',
    });
    expect(component.error()).toBeNull();
    expect(component.loading()).toBe(false);
  });

  it('sets guardrailError signal on 422 with reason=prompt_injection', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 422, detail: { message: 'Suspicious text detected.', reason: 'prompt_injection' } })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    expect(component.guardrailError()?.reason).toBe('prompt_injection');
    expect(component.error()).toBeNull();
  });

  it('sets guardrailError signal on 400 with reason=moderation', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 400, detail: { message: 'Input flagged by moderation: hate', reason: 'moderation' } })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    expect(component.guardrailError()?.reason).toBe('moderation');
    expect(component.error()).toBeNull();
  });

  it('renders guardrail warning block when guardrailError is set', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 422, detail: { message: 'Email address detected.', reason: 'pii' } })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    const warning: HTMLElement = fixture.nativeElement.querySelector('.guardrail-warning');
    expect(warning).toBeTruthy();
    expect(warning.textContent).toContain('Email address detected.');
    expect(warning.getAttribute('data-reason')).toBe('pii');
  });

  it('does not render error-msg paragraph when guardrail error occurs', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 422, detail: { message: 'IBAN detected.', reason: 'pii' } })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    const errorParagraph = fixture.nativeElement.querySelector('.error-msg');
    expect(errorParagraph).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// submit() — generic (non-guardrail) error path
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — submit() generic errors', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('sets error signal on 500 server error', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 500, detail: 'Internal server error' })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    expect(component.error()).toContain('500');
    expect(component.guardrailError()).toBeNull();
  });

  it('sets error signal on 429 rate-limit error', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 429, detail: 'Rate limit reached' })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    expect(component.error()).toContain('429');
    expect(component.guardrailError()).toBeNull();
  });

  it('does not render guardrail-warning on generic errors', () => {
    const { component, estimationService, fixture } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 500, detail: 'Internal server error' })),
    );
    setRequiredSubmitFields(component);
    component.submit();
    fixture.detectChanges();

    const warning = fixture.nativeElement.querySelector('.guardrail-warning');
    expect(warning).toBeTruthy();
    expect(warning.getAttribute('data-reason')).toBe('form');
  });
});

// ---------------------------------------------------------------------------
// refProjects management
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — refProjects management', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('starts with an empty refProjects array', () => {
    const { component } = setup();
    expect(component.refProjects).toEqual([]);
  });

  it('addRefProject() appends a blank project entry', () => {
    const { component } = setup();
    component.addRefProject();
    expect(component.refProjects.length).toBe(1);
    expect(component.refProjects[0]).toEqual({
      name: '', description: '', total_hours: null, total_cost: null,
    });
  });

  it('addRefProject() called twice produces two entries', () => {
    const { component } = setup();
    component.addRefProject();
    component.addRefProject();
    expect(component.refProjects.length).toBe(2);
  });

  it('removeRefProject() pops the last entry', () => {
    const { component } = setup();
    component.addRefProject();
    component.addRefProject();
    component.removeRefProject();
    expect(component.refProjects.length).toBe(1);
  });

  it('removeRefProject() on empty array does not throw', () => {
    const { component } = setup();
    expect(() => component.removeRefProject()).not.toThrow();
    expect(component.refProjects.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// submit() — reference_projects in payload
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — submit() reference_projects payload', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('omits reference_projects from payload when array is empty', () => {
    const { component, estimationService } = setup();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.submit();

    const formData = streamSpy.mock.calls[0][1] as FormData;
    expect(formData.get('reference_projects')).toBeNull();
  });

  it('includes reference_projects in payload when valid entries exist', () => {
    const { component, estimationService } = setup();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.addRefProject();
    component.refProjects[0].name = 'HR Tool v1';
    component.refProjects[0].description = 'Basic CRUD app';
    component.refProjects[0].total_hours = 200;
    component.refProjects[0].total_cost = 15000;
    component.submit();

    const formData = streamSpy.mock.calls[0][1] as FormData;
    expect(JSON.parse(formData.get('reference_projects') as string)).toEqual([
      { name: 'HR Tool v1', description: 'Basic CRUD app', total_hours: 200, total_cost: 15000 },
    ]);
  });

  it('filters out entries with empty name before sending', () => {
    const { component, estimationService } = setup();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.addRefProject();
    component.refProjects[0].name = '';
    component.refProjects[0].description = 'Has description but no name';
    component.submit();

    expect(streamSpy).not.toHaveBeenCalled();
    expect(component.error()).toContain('Complete all fields');
  });

  it('filters out entries with empty description before sending', () => {
    const { component, estimationService } = setup();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.addRefProject();
    component.refProjects[0].name = 'Has name but no description';
    component.refProjects[0].description = '';
    component.submit();

    expect(streamSpy).not.toHaveBeenCalled();
    expect(component.error()).toContain('Complete all fields');
  });

  it('sends only valid entries when mix of valid and empty exists', () => {
    const { component, estimationService } = setup();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(new Observable(() => {}));
    setRequiredSubmitFields(component);
    component.addRefProject();
    component.refProjects[0].name = 'Valid Project';
    component.refProjects[0].description = 'Has both fields';
    component.refProjects[0].total_hours = 10;
    component.refProjects[0].total_cost = 1000;
    component.addRefProject(); // second entry left blank
    component.submit();

    expect(streamSpy).not.toHaveBeenCalled();
    expect(component.error()).toContain('Complete all fields');
  });
});

// ---------------------------------------------------------------------------
// attachment signals — fileIcon / formatSize / formatCost helpers
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — attachment helpers', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('starts with empty attachments', () => {
    const { component } = setup();
    expect(component.attachments()).toEqual([]);
  });

  it('fileIcon returns picture_as_pdf for .pdf files', () => {
    const { component } = setup();
    expect(component.fileIcon(makeFile('spec.pdf', 'application/pdf'))).toBe('picture_as_pdf');
  });

  it('fileIcon returns description for .docx files', () => {
    const { component } = setup();
    expect(component.fileIcon(makeFile('spec.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))).toBe('description');
  });

  it('fileIcon returns text_snippet for .txt files', () => {
    const { component } = setup();
    expect(component.fileIcon(makeFile('notes.txt', 'text/plain'))).toBe('text_snippet');
  });

  it('fileIcon returns attach_file for unknown types', () => {
    const { component } = setup();
    expect(component.fileIcon(makeFile('data.csv', 'text/csv'))).toBe('attach_file');
  });

  it('formatSize formats bytes below 1 KB', () => {
    const { component } = setup();
    expect(component.formatSize(512)).toBe('512 B');
  });

  it('formatSize formats bytes in KB range', () => {
    const { component } = setup();
    expect(component.formatSize(2048)).toBe('2.0 KB');
  });

  it('formatSize formats bytes in MB range', () => {
    const { component } = setup();
    expect(component.formatSize(1.5 * 1024 * 1024)).toBe('1.5 MB');
  });

  it('formatCost returns dollar-prefixed string with 6 decimal places', () => {
    const { component } = setup();
    expect(component.formatCost(0.00042)).toBe('$0.000420');
  });
});

// ---------------------------------------------------------------------------
// attachment management — onFilesSelected / removeAttachment
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — attachment management', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());


  it('onFilesSelected() adds files to the attachments signal', () => {
    const { component } = setup();
    const file = new File(['hello'], 'report.pdf', { type: 'application/pdf' });
    const input = document.createElement('input');
    Object.defineProperty(input, 'files', { value: makeFileList(file) });
    const event = { target: input } as unknown as Event;

    component.onFilesSelected(event);

    expect(component.attachments().length).toBe(1);
    expect(component.attachments()[0].name).toBe('report.pdf');
  });

  it('onFilesSelected() accumulates files across multiple calls', () => {
    const { component } = setup();
    const fileA = new File(['a'], 'a.pdf', { type: 'application/pdf' });
    const fileB = new File(['b'], 'b.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });

    for (const f of [fileA, fileB]) {
      const input = document.createElement('input');
      Object.defineProperty(input, 'files', { value: makeFileList(f) });
      component.onFilesSelected({ target: input } as unknown as Event);
    }

    expect(component.attachments().length).toBe(2);
  });

  it('removeAttachment() removes the file at the given index', () => {
    const { component } = setup();
    const fileA = new File(['a'], 'a.pdf', { type: 'application/pdf' });
    const fileB = new File(['b'], 'b.txt', { type: 'text/plain' });
    const input = document.createElement('input');
    Object.defineProperty(input, 'files', { value: makeFileList(fileA, fileB) });
    component.onFilesSelected({ target: input } as unknown as Event);

    component.removeAttachment(0);

    expect(component.attachments().length).toBe(1);
    expect(component.attachments()[0].name).toBe('b.txt');
  });

  it('dragOver signal is initially false', () => {
    const { component } = setup();
    expect(component.dragOver()).toBe(false);
  });

  it('onDragOver() sets dragOver to true', () => {
    const { component } = setup();
    const event = new Event('dragover') as DragEvent;
    component.onDragOver(event);
    expect(component.dragOver()).toBe(true);
  });

  it('onDragLeave() resets dragOver to false', () => {
    const { component } = setup();
    component.dragOver.set(true);
    component.onDragLeave(new Event('dragleave') as DragEvent);
    expect(component.dragOver()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// submit() with attachments — session-based multipart path
// ---------------------------------------------------------------------------

const MOCK_SESSION_RESULT = {
  estimation: '## Phase 1\n40h',
  model: 'gpt-4o-mini',
  response_id: 'resp-123',
  input_tokens: 300,
  output_tokens: 120,
  turn_cost_usd: 0.000042,
  total_cost_usd: 0.000042,
  estimated_input_tokens: 280,
  estimated_precall_cost_usd: null,
  requirements: null,
  pre_call_cost_usd: null,
  prompt_version: 'v1',
};

describe('EstimationFormComponent — submit() with attachments', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('uses the existing session to submit multipart payload', () => {
    const { component, httpMock, estimationService } = setupWithAttachment();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next('partial response');
        subscriber.complete();
      }),
    );

    component.submit();

    expect(streamSpy).toHaveBeenCalledWith('sid-bootstrap', expect.any(FormData), 'v1');
    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: {
        project_name: 'PortalX',
        assumed_team_size: 3,
        mentioned_technologies: ['angular'],
        agreed_scope: 'MVP',
      },
      history: [{ role: 'user', content: 'x' }, { role: 'assistant', content: 'y' }],
      turn_count: 1,
    });
  });

  it('sends attachments as FormData to the session estimate endpoint', () => {
    const { component, httpMock, estimationService } = setupWithAttachment();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next('streamed');
        subscriber.complete();
      }),
    );

    component.submit();

    const formData = streamSpy.mock.calls[0][1];
    expect(formData).toBeInstanceOf(FormData);
    expect((formData as FormData).getAll('attachments').length).toBe(1);
    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: { project_name: null, assumed_team_size: null, mentioned_technologies: [], agreed_scope: null },
      history: [],
      turn_count: 0,
    });
  });

  it('includes prompt_version as a query param', () => {
    const { component, httpMock, estimationService } = setupWithAttachment();
    const streamSpy = vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next('streamed');
        subscriber.complete();
      }),
    );
    component.form.prompt_version = 'v2';

    component.submit();

    expect(streamSpy).toHaveBeenCalledWith('sid-bootstrap', expect.any(FormData), 'v2');
    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: { project_name: null, assumed_team_size: null, mentioned_technologies: [], agreed_scope: null },
      history: [],
      turn_count: 0,
    });
  });

  it('sets inlineResult signal on success', () => {
    const { component, httpMock, fixture, estimationService } = setupWithAttachment();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next(JSON.stringify(MOCK_SESSION_RESULT));
        subscriber.complete();
      }),
    );

    component.submit();

    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: { project_name: null, assumed_team_size: null, mentioned_technologies: [], agreed_scope: null },
      history: [],
      turn_count: 0,
    });
    fixture.detectChanges();

    expect(component.responsePayload()).toEqual(MOCK_SESSION_RESULT);
    expect(component.streamingResult()).toContain('## Phase 1');
    expect(component.loading()).toBe(false);
  });

  it('renders the inline result panel when inlineResult is set', () => {
    const { component, httpMock, fixture, estimationService } = setupWithAttachment();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next(JSON.stringify(MOCK_SESSION_RESULT));
        subscriber.complete();
      }),
    );

    component.submit();

    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: { project_name: null, assumed_team_size: null, mentioned_technologies: [], agreed_scope: null },
      history: [],
      turn_count: 0,
    });
    component.activeTab.set('response');
    fixture.detectChanges();

    const panel: HTMLElement = fixture.nativeElement.querySelector('app-estimation-result');
    expect(panel).toBeTruthy();
  });

  it('shows error and clears loading on estimation failure (503)', () => {
    const { component, estimationService, fixture } = setupWithAttachment();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => subscriber.error({ status: 503, detail: 'Service unavailable' })),
    );

    component.submit();

    fixture.detectChanges();

    expect(component.error()).toContain('503');
    expect(component.loading()).toBe(false);
    expect(component.inlineResult()).toBeNull();
  });

  it('shows error on 422 unsupported attachment type', () => {
    const { component, estimationService, fixture } = setupWithAttachment();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber =>
        subscriber.error({ status: 422, detail: "Unsupported attachment type 'application/zip' for file 'archive.zip'." }),
      ),
    );

    component.submit();

    fixture.detectChanges();

    expect(component.error()).toContain('422');
    expect(component.loading()).toBe(false);
  });

  it('also uses session endpoint when there are no attachments', () => {
    const { component, httpMock, estimationService } = setup();
    vi.spyOn(estimationService, 'createWithAttachmentsStream').mockReturnValue(
      new Observable(subscriber => {
        subscriber.next('streamed');
        subscriber.complete();
      }),
    );
    setRequiredSubmitFields(component);

    component.submit();

    httpMock.expectOne(`${SESSIONS_BASE}/sid-bootstrap`).flush({
      session_id: 'sid-bootstrap',
      project_metadata: { project_name: null, assumed_team_size: null, mentioned_technologies: [], agreed_scope: null },
      history: [],
      turn_count: 0,
    });
  });
});
