import { Component, OnInit, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from './core/auth/auth.service';
import { EstimationService } from './features/estimations/estimation.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatToolbarModule, MatButtonModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  activeModel = signal<string | null>(null);

  constructor(
    readonly auth: AuthService,
    private readonly estimationService: EstimationService,
  ) {}

  ngOnInit() {
    if (!this.auth.isLoggedIn()) {
      return;
    }
    this.estimationService.getRuntimeModels().subscribe({
      next: payload => {
        this.activeModel.set(payload.models?.LLM_MODEL?.effective ?? null);
      },
      error: () => {
        this.activeModel.set(null);
      },
    });
  }
}
