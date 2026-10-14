# Nexus Loop screen

The operator screen is a React, TypeScript, Vite, and Tailwind application. It renders the backend-owned screen model from `GET /api/screen`; it does not read reports or corpus data directly and does not calculate report metrics in the browser.

## Local development

Install dependencies once, then start the backend and frontend together from `nexus-loop/screen/`:

```powershell
npm install
npm run dev
```

`npm run dev` starts the replay engine on port 8719, runs a fresh detect/diagnose/prescribe analysis of the original kit in the API process on port 8765, and starts Vite on the first available local development port. An API already on that port is reused only when its health response confirms that it is a live session over this same kit. The combined command stops the app if either process it started later fails.

Approval runs the selected proposal through replay at that moment. Rejection and deferral do not run replay. Decisions and outcomes live only in memory and disappear when the backend stops.

To run the three processes separately, start the replay engine first:

```powershell
npm run dev:replay
npm run dev:backend
npm run dev:frontend
```

Vite proxies same-origin `/api` requests to `http://127.0.0.1:8765`. The bundled Python server intentionally does not
enable cross-origin access, so an arbitrary webpage cannot consume replay budget or mutate the current review session.
For a remote deployment, place the frontend and API behind the same origin (or a trusted reverse proxy).

## Verify and build

```powershell
npm test
npm run build
```

The production build is written to `dist/`. The Python server serves that directory at `/` by default, so production uses same-origin `/api` requests and has no remote runtime assets.
