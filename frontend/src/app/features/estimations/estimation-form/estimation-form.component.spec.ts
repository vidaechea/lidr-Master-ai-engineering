import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';

import { EstimationFormComponent } from './estimation-form.component';
import { environment } from '../../../../environments/environment';

const ESTIMATE_URL = `${environment.apiUrl}/v1/estimations`;

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
  fixture.detectChanges();
  return { fixture, component, httpMock };
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
    const { component, httpMock } = setup();
    component.error.set('previous error');
    component.guardrailError.set({ message: 'old', reason: 'pii' });

    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    expect(component.error()).toBeNull();
    expect(component.guardrailError()).toBeNull();

    httpMock.expectOne(ESTIMATE_URL).flush({ id: 'est-new' });
  });

  it('sets loading=true while request is in-flight', () => {
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    expect(component.loading()).toBe(true);
    httpMock.expectOne(ESTIMATE_URL).flush({ id: 'est-new' });
  });
});

// ---------------------------------------------------------------------------
// submit() — guardrail error paths
// ---------------------------------------------------------------------------

describe('EstimationFormComponent — submit() guardrail errors', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('sets guardrailError signal on 422 with reason=pii', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: { message: 'Email address detected.', reason: 'pii' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    expect(component.guardrailError()).toEqual({
      message: 'Email address detected.',
      reason: 'pii',
    });
    expect(component.error()).toBeNull();
    expect(component.loading()).toBe(false);
  });

  it('sets guardrailError signal on 422 with reason=prompt_injection', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: { message: 'Suspicious text detected.', reason: 'prompt_injection' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    expect(component.guardrailError()?.reason).toBe('prompt_injection');
    expect(component.error()).toBeNull();
  });

  it('sets guardrailError signal on 400 with reason=moderation', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: { message: 'Input flagged by moderation: hate', reason: 'moderation' } },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();

    expect(component.guardrailError()?.reason).toBe('moderation');
    expect(component.error()).toBeNull();
  });

  it('renders guardrail warning block when guardrailError is set', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: { message: 'Email address detected.', reason: 'pii' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();

    const warning: HTMLElement = fixture.nativeElement.querySelector('.guardrail-warning');
    expect(warning).toBeTruthy();
    expect(warning.textContent).toContain('Email address detected.');
    expect(warning.getAttribute('data-reason')).toBe('pii');
  });

  it('does not render error-msg paragraph when guardrail error occurs', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: { message: 'IBAN detected.', reason: 'pii' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
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
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: 'Internal server error' },
      { status: 500, statusText: 'Internal Server Error' },
    );
    fixture.detectChanges();

    expect(component.error()).toContain('500');
    expect(component.guardrailError()).toBeNull();
  });

  it('sets error signal on 429 rate-limit error', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: 'Rate limit reached' },
      { status: 429, statusText: 'Too Many Requests' },
    );
    fixture.detectChanges();

    expect(component.error()).toContain('429');
    expect(component.guardrailError()).toBeNull();
  });

  it('does not render guardrail-warning on generic errors', () => {
    const { component, httpMock, fixture } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    httpMock.expectOne(ESTIMATE_URL).flush(
      { detail: 'Internal server error' },
      { status: 500, statusText: 'Internal Server Error' },
    );
    fixture.detectChanges();

    const warning = fixture.nativeElement.querySelector('.guardrail-warning');
    expect(warning).toBeNull();
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
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.submit();

    const req = httpMock.expectOne(ESTIMATE_URL);
    expect(req.request.body['reference_projects']).toBeUndefined();
    req.flush({ id: 'est-1' });
  });

  it('includes reference_projects in payload when valid entries exist', () => {
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.addRefProject();
    component.refProjects[0].name = 'HR Tool v1';
    component.refProjects[0].description = 'Basic CRUD app';
    component.refProjects[0].total_hours = 200;
    component.refProjects[0].total_cost = 15000;
    component.submit();

    const req = httpMock.expectOne(ESTIMATE_URL);
    expect(req.request.body['reference_projects']).toEqual([
      { name: 'HR Tool v1', description: 'Basic CRUD app', total_hours: 200, total_cost: 15000 },
    ]);
    req.flush({ id: 'est-2' });
  });

  it('filters out entries with empty name before sending', () => {
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.addRefProject();
    component.refProjects[0].name = '';
    component.refProjects[0].description = 'Has description but no name';
    component.submit();

    const req = httpMock.expectOne(ESTIMATE_URL);
    expect(req.request.body['reference_projects']).toBeUndefined();
    req.flush({ id: 'est-3' });
  });

  it('filters out entries with empty description before sending', () => {
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.addRefProject();
    component.refProjects[0].name = 'Has name but no description';
    component.refProjects[0].description = '';
    component.submit();

    const req = httpMock.expectOne(ESTIMATE_URL);
    expect(req.request.body['reference_projects']).toBeUndefined();
    req.flush({ id: 'est-4' });
  });

  it('sends only valid entries when mix of valid and empty exists', () => {
    const { component, httpMock } = setup();
    component.form.transcription = VALID_TRANSCRIPTION;
    component.addRefProject();
    component.refProjects[0].name = 'Valid Project';
    component.refProjects[0].description = 'Has both fields';
    component.addRefProject(); // second entry left blank
    component.submit();

    const req = httpMock.expectOne(ESTIMATE_URL);
    const sent = req.request.body['reference_projects'];
    expect(sent.length).toBe(1);
    expect(sent[0].name).toBe('Valid Project');
    req.flush({ id: 'est-5' });
  });
});
