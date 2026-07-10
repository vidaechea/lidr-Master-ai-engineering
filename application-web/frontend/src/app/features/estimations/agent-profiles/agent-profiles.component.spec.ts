import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { AgentProfilesComponent } from './agent-profiles.component';
import { RagEstimationService } from '../rag-estimation.service';

describe('AgentProfilesComponent', () => {
  let component: AgentProfilesComponent;
  let fixture: ComponentFixture<AgentProfilesComponent>;
  let ragService: {
    listAgentProfiles: ReturnType<typeof vi.fn>;
    createAgentProfile: ReturnType<typeof vi.fn>;
    updateAgentProfile: ReturnType<typeof vi.fn>;
    deleteAgentProfile: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    const ragServiceSpy = {
      listAgentProfiles: vi.fn().mockReturnValue(of([])),
      createAgentProfile: vi.fn().mockReturnValue(
        of({
          id: '1',
          name: 'Default',
          persona: null,
          config: {},
          is_default: true,
          created_at: '2026-07-10T00:00:00Z',
          updated_at: '2026-07-10T00:00:00Z',
        })
      ),
      updateAgentProfile: vi.fn().mockReturnValue(of({})),
      deleteAgentProfile: vi.fn().mockReturnValue(of(void 0)),
    };

    await TestBed.configureTestingModule({
      imports: [AgentProfilesComponent],
      providers: [{ provide: RagEstimationService, useValue: ragServiceSpy }],
    }).compileComponents();

    ragService = TestBed.inject(RagEstimationService) as unknown as {
      listAgentProfiles: ReturnType<typeof vi.fn>;
      createAgentProfile: ReturnType<typeof vi.fn>;
      updateAgentProfile: ReturnType<typeof vi.fn>;
      deleteAgentProfile: ReturnType<typeof vi.fn>;
    };

    fixture = TestBed.createComponent(AgentProfilesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load profiles on init', () => {
    expect(ragService.listAgentProfiles).toHaveBeenCalledTimes(1);
    expect(component.profiles()).toEqual([]);
  });

  it('should create a new profile when saving without edit id', () => {
    component.startNew();
    component.draftName = 'Conservative';
    component.draftDefault = true;

    component.save();

    expect(ragService.createAgentProfile).toHaveBeenCalledTimes(1);
  });

  it('should delete profile and reload list', () => {
    component.remove({
      id: '1',
      name: 'ToDelete',
      persona: null,
      config: {},
      is_default: false,
      created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:00Z',
    });

    expect(ragService.deleteAgentProfile).toHaveBeenCalledWith('1');
    expect(ragService.listAgentProfiles).toHaveBeenCalledTimes(2);
  });
});
