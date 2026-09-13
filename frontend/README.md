# OCDFG Layout – frontend

Create React App + MUI. Setup and usage are described in the repository root README.

```bash
npm install
npm start      # dev server on http://localhost:3000 (expects the backend on :8000)
npm run build  # production build in build/
```

Set `REACT_APP_API_HOST` to point at a backend elsewhere (copy `.env.example` to `.env`).

```
src/Nav.js                    sidebar + routes
src/pages/DataPreparation.js  upload / delete OCEL logs
src/pages/OCDFGLayout.js      layout view: object-type and frequency filters, zoom, edge info
src/services/API.js           backend calls
src/Config.js                 object-type colour palette
```
