# OCDFG Layout [![DOI](https://zenodo.org/badge/1368245355.svg)](https://doi.org/10.5281/zenodo.22739339)

A process mining tool: layout algorithm and interactive viewer for **object-centric directly-follows graphs (OC-DFG)** discovered from OCEL 2.0 event logs.

A project by **Deoksang Lee**, **Minseok Song** and **Wil M.P. van der Aalst**.

An OCEL 2.0 log is split into one directly-follows graph per object type. Every activity gets a
common rank (ILP), each object type is laid out on its own vertical axis, and the axes are merged
one by one so that activities shared between object types line up. Filtering (by object type or
edge frequency) re-runs only the placement step on the cached layout, so the graph stays stable
and the node movement can be measured.

```
backend/    FastAPI server + the `ocdfg_layout` Python package (the algorithm)
frontend/   React web app: upload logs, draw the layout, filter, zoom
```

## Demo

![OCDFG Layout demo](docs/ocdfg_layout_record.gif)

Full-resolution recording: [docs/ocdfg_layout_record.mp4](docs/ocdfg_layout_record.mp4)

## Requirements

- Python 3.10+ and a **Gurobi** license (`gurobipy` is used for rank assignment; the free
  academic license is enough)
- Node.js 18+

## Quick start

```bash
# backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# frontend (second terminal)
cd frontend
npm install
npm start          # http://localhost:3000
```

Then open http://localhost:3000:

1. **Data Preparation** – upload an OCEL 2.0 JSON file under a name.
2. **OCDFG Layout** – pick the log and press *Visualize*. Untick object types and/or move the
   edge-frequency slider, then *Apply* to filter. Click an edge for its source, target and
   frequency. Zoom with the slider or Ctrl + mouse wheel; *Reset* fits the whole drawing again.

## Backend

Uploaded logs are stored in `backend/data/<name>/`; seven preprocessed sample logs
(blockchain, hinge, hiring, hospital, logistics, o2c, p2p) are included, so the app works right
after start-up. Computed layouts are cached as pickles in `backend/pickles/` (git-ignored) –
the filter endpoints reload that pickle, so a filter never recomputes the ranks. Override the
locations with `OCDFG_DATA_DIR` and `OCDFG_PICKLE_DIR`.

### API

| Method | Path | Body / query | Description |
| --- | --- | --- | --- |
| GET | `/ocel-list` | – | Names of uploaded logs |
| POST | `/ocel-upload` | `{data_name, d}` | `d` is the OCEL 2.0 JSON as a string |
| GET | `/ocel-info` | `?data_name=` | Object types of a log |
| DELETE | `/ocel-remove` | `{data_name}` | Delete an uploaded log |
| GET | `/ocel-process-layout` | `?data_dir=` | Compute the layout; returns `output`, `pickle_path`, `layout_time_seconds` |
| POST | `/filter-layout` | `{pickle_path, object_types?, filter_value?}` | Keep only the given object types and/or the top `filter_value` % of edges by frequency (what the UI uses) |
| POST | `/filter-layout-by-value` | `{pickle_path, filter_value}` | Frequency filter only |
| POST | `/filter-layout-from-pickle` | `{pickle_path, kept_edge_keys}` | Keep an explicit set of edge keys (`"source-target-type"`) |

`output` contains `nodes` (with `nodes_visualized`: one sub-circle per object type), `edges`
(polyline `data` per original edge), `object_axis_order`, `edge_crosses`, `maxFreq`/`minFreq`,
`radius` and, for filters, `movement`.

### Tuning

| Where | Setting | Meaning |
| --- | --- | --- |
| `ocdfg_layout/conf.py` | `RANK_HEIGHT`, `ORDER_WIDTH`, `NODE_GAP`, `NODE_MIN_WIDTH`, `NODE_CHAR_WIDTH`, `RADIUS`, … | Drawing geometry (SVG user units) |
| `ocdfg_layout/conf.py` | `EDGE_STRAIGHTENING` | `'vertical'` (default), `'diagonal'` or `None` |
| `ocdfg_layout/conf.py` | `AXIS_SLACK_SLOTS` | Extra order slots per axis side available to the crossing reduction (2) |
| `MultiObjectGraph` | `LAMBDA_EDGE_CROSS`, `LAMBDA_AXIS_DIST` | Weights of the axis-position cost (10 / 0.3) |

The frontend scales its node/edge sizes from the `radius` in the response, so changing the
geometry only needs a backend restart.

## Frontend

Create React App + MUI. `src/pages/OCDFGLayout.js` renders the SVG; `src/services/API.js` wraps
the endpoints above. The backend URL defaults to `http://localhost:8000`; set
`REACT_APP_API_HOST` (see `frontend/.env.example`) to change it. `npm run build` produces a
static build in `frontend/build/`.

## Package layout

```
backend/
  main.py                 FastAPI app
  ocdfg_layout/
    MultiObjectGraph.py   the OC-DFG layout (rank assignment, per-type layout, axis merging,
                          crossing reduction, placement) and filtering
    ObjectGraph.py        laid-out graph of one object type (ObjectNode / ObjectEdge)
    preprocess.py         OCEL 2.0 JSON -> case variants per object type
    conf.py               drawing constants
    process_layout/       single-object layered layout used per object type
      Graph.py            backbone, virtual nodes, component balancing, crossing reduction
      Node.py, Edge.py, Component.py, geometry.py, Util.py
frontend/
  src/pages/DataPreparation.js   upload / delete logs
  src/pages/OCDFGLayout.js       layout view, filters, zoom
  src/services/API.js            backend calls
```
