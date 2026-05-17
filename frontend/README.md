# Frontend — Angular SPA

Modern, responsive user interface built with Angular 21. Provides project and estimation management with JWT-based authentication.

---

## Overview

The frontend is the primary user interface for Estimator. It allows users to:

- 🔐 **Authenticate** — Register, login, and manage JWT tokens
- 📦 **Manage projects** — Create, list, and organize estimation projects
- 🎯 **Create estimations** — Submit meeting transcriptions for AI-powered effort estimates
- 📊 **View results** — Display and analyze estimation results
- ⚙️ **Configure preferences** — User settings and API key management

---

## Development Setup

### Prerequisites

- Node.js 18+ and npm 9+
- Angular CLI 21+

### Installation

```bash
cd frontend
npm install
```

### Development Server

Start the local development server with hot reload:

```bash
npm start
```

Then open your browser and navigate to `http://localhost:4200/`

The application will automatically reload whenever you modify source files.

---

## Building for Production

```bash
npm run build
```

Build artifacts are stored in the `dist/` directory. The build is optimized for performance and production deployment.

---

## Testing

### Unit Tests (Vitest)

Run unit tests with the Vitest test runner:

```bash
npm test
```

Watch mode for development:

```bash
npm run test:watch
```

### End-to-End Tests (Playwright)

Run end-to-end tests:

```bash
npm run e2e
```

---

## Project Structure

```
frontend/src/
├── index.html              # Entry HTML file
├── main.ts                 # Application bootstrap
├── styles.scss             # Global styles
├── app/
│   ├── app.component.*     # Root component
│   ├── features/           # Business modules
│   │   ├── auth/          # Authentication feature
│   │   ├── projects/      # Projects management
│   │   └── estimations/   # Estimations feature
│   ├── core/              # Singleton services, guards, interceptors
│   │   ├── services/      # Core services (auth, API)
│   │   ├── guards/        # Route guards
│   │   └── interceptors/  # HTTP interceptors
│   └── shared/            # Reusable components, pipes, directives
├── environments/          # Environment-specific config
└── assets/               # Static assets (images, icons)
```

---

## Key Features

### Authentication (`features/auth/`)

- User registration and login
- JWT token management (access + refresh)
- OAuth2 integration (extensible)
- Protected routes with `AuthGuard`
- Automatic token refresh via HTTP interceptor

### Projects (`features/projects/`)

- List user's projects with pagination
- Create new projects
- Edit project details
- Delete projects with confirmation
- Filter and search projects

### Estimations (`features/estimations/`)

- Create new estimations from transcriptions
- Support for synchronous and asynchronous processing
- Real-time status polling for async tasks
- Display estimation results in readable format
- Cost breakdown and statistics
- Download results as markdown/JSON

### Core Services (`core/services/`)

- **AuthService** — Token management, login/signup
- **ApiService** — Centralized HTTP client with auth headers
- **ProjectService** — Project CRUD operations
- **EstimationService** — Estimation lifecycle management

---

## HTTP Interceptors

### AuthInterceptor
- Attaches JWT access token to all requests
- Handles token refresh on 401 responses
- Retries failed requests with new token

### ErrorInterceptor
- Catches and logs HTTP errors
- Displays user-friendly error messages
- Handles specific error scenarios (401, 403, 404, 500)

---

## Routing

Main application routes:

| Path | Component | Protected |
|---|---|---|
| `/` | Welcome / Redirect | No |
| `/auth/login` | Login page | No |
| `/auth/register` | Registration page | No |
| `/projects` | Projects list | ✅ Yes |
| `/projects/:id` | Project detail | ✅ Yes |
| `/estimations` | Estimations list | ✅ Yes |
| `/estimations/new` | Create estimation | ✅ Yes |
| `/estimations/:id` | Estimation detail | ✅ Yes |

Routes marked with ✅ require authentication. Unauthenticated users are redirected to login.

---

## Environment Configuration

Environment-specific settings in `src/environments/`:

- `environment.ts` — Development
- `environment.prod.ts` — Production

**Example:**
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
  aiEngineUrl: 'http://localhost:8001'
};
```

---

## Styling

- **Framework**: SCSS with nested selectors
- **Component styles**: Scoped to components via View Encapsulation
- **Global styles**: `styles.scss` for resets, typography, variables
- **Design system**: CSS variables for colors, spacing, typography

---

## Stack

| Package | Version | Purpose |
|---|---|---|
| Angular | 21.x | Framework |
| TypeScript | 5.2+ | Language |
| RxJS | 7.8+ | Reactive programming |
| Vitest | 0.34+ | Unit testing |
| Playwright | 1.40+ | E2E testing |
| Prettier | 3.0+ | Code formatting |
| ESLint | 8.5+ | Linting |

---

## Code Scaffolding

Generate Angular artifacts with the CLI:

```bash
# Component
ng generate component component-name

# Service
ng generate service service-name

# Module
ng generate module module-name

# Guard
ng generate guard guard-name

# Interceptor
ng generate interceptor interceptor-name
```

For a complete list of available schematics:

```bash
ng generate --help
```

---

## Troubleshooting

### Playwright/Chromium Errors (Codespaces)

If you see errors like `libatk-1.0.so.0: cannot open shared object file`:

```bash
npx playwright install-deps chromium
npx playwright install chromium
npm test
```

### Module Resolution Issues

Clear Angular cache:

```bash
ng cache clean
rm -rf .angular dist node_modules
npm install
```

### Development Server Won't Start

1. Check if port 4200 is already in use
2. Kill existing processes: `lsof -ti:4200 | xargs kill -9`
3. Clear node_modules: `rm -rf node_modules && npm install`

---

## Resources

- [Angular Official Docs](https://angular.dev)
- [Angular CLI Overview](https://angular.dev/tools/cli)
- [TypeScript Handbook](https://www.typescriptlang.org/docs)
- [RxJS Documentation](https://rxjs.dev)

---

## Related Documentation

- [Main README](../README.md) — Project overview
- [Backend README](../backend/README.md) — Business API
- [AI Engine README](../ai-engine/README.md) — LLM engine

---

## License

MIT

