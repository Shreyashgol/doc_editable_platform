# Document AI Platform — Frontend

React + TypeScript SPA for uploading drawings, watching processing, editing extracted symbols
on a canvas, browsing the relationship graph, and semantic search.

## Stack
- **React 18 + TypeScript**, Vite build/dev server.
- **React Query** for server state (caching, polling document status until terminal).
- **Zustand** for UI state (`auth` tokens, `canvas` selection/zoom/pan).
- **React Konva** for the symbol canvas (drag / resize / rotate / zoom / pan / multi-select).
- **axios** client with bearer-token injection and automatic refresh-on-401.

## Pages
| Route | Page | Purpose |
|-------|------|---------|
| `/login` | Login/Register | obtain JWT |
| `/` | Dashboard | document list with live status |
| `/upload` | Upload | submit a PDF, redirect to canvas |
| `/documents/:id/canvas` | Canvas | edit symbols (Konva) + property editor side panel |
| `/documents/:id/graph` | Graph | relationship graph viewer |
| `/search` | Search | cross-modal text → symbol vector search |

## Develop
```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000
npm run typecheck && npm run test && npm run build
```

## Notes
- The canvas persists every drag/resize/rotate via `PATCH /symbols/{id}`, which the backend
  records as an immutable version (full edit history).
- Types in `src/types/api.ts` mirror the backend Pydantic response models.
