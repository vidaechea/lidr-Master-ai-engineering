import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, _state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isLoggedIn()) {
    return true;
  }

  // If a token exists but user state is not yet hydrated, validate with /me.
  if (auth.accessToken) {
    return auth.fetchCurrentUser().pipe(
      map(() => true),
      catchError(() => of(router.createUrlTree(['/auth/login']))),
    );
  }

  return router.createUrlTree(['/auth/login']);
};
