import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface Project {
  id: string;
  name: string;
  description: string | null;
  project_type: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  project_type?: string;
}

@Injectable({ providedIn: 'root' })
export class ProjectService {
  private readonly base = `${environment.apiUrl}/v1/projects`;
  readonly projects = signal<Project[]>([]);

  constructor(private http: HttpClient) {}

  load() {
    return this.http.get<Project[]>(this.base).pipe(
      tap(projects => this.projects.set(projects)),
    );
  }

  create(data: ProjectCreate) {
    return this.http.post<Project>(this.base, data);
  }

  update(id: string, data: Partial<ProjectCreate>) {
    return this.http.patch<Project>(`${this.base}/${id}`, data);
  }

  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
