"""FastAPI server for the OC-DFG layout web app.

Run from this directory:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Uploaded logs are stored under DATA_DIR/<data_name>/ and generated layouts are
cached as pickles under PICKLE_DIR so that filtering can reuse them.
"""
import json
import os
import pickle
import shutil
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocdfg_layout import MultiObjectGraph
from ocdfg_layout.preprocess import ocel_to_layout_log

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("OCDFG_DATA_DIR", os.path.join(BASE_DIR, "data"))
PICKLE_DIR = os.environ.get("OCDFG_PICKLE_DIR", os.path.join(BASE_DIR, "pickles"))

app = FastAPI(title="OC-DFG Layout API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def data_path(data_name: str, *parts: str) -> str:
    return os.path.join(DATA_DIR, data_name, *parts)


def load_pickle(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)


# -----------------------------------------------------------------------------
# Data management
# -----------------------------------------------------------------------------
class DataRemoveItem(BaseModel):
    data_name: str


class DataItem(BaseModel):
    data_name: str
    d: str  # OCEL 2.0 JSON as a string


@app.get("/ocel-list")
def get_ocel_list():
    os.makedirs(DATA_DIR, exist_ok=True)
    dirs = sorted((f for f in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, f))), reverse=True)
    return {"files": dirs}


@app.get("/ocel-info")
def get_ocel_info(data_name: str):
    object_types = load_pickle(data_path(data_name, "object_types.pkl"))
    return {"object_types": object_types}


@app.delete("/ocel-remove")
def remove_ocel(item: DataRemoveItem):
    try:
        shutil.rmtree(data_path(item.data_name), ignore_errors=True)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/ocel-upload")
def upload_ocel(item: DataItem):
    d = json.loads(item.d)
    eventlog_org_df, log_preprocessed = ocel_to_layout_log(d)

    try:
        data_dir = data_path(item.data_name)
        os.makedirs(data_dir, exist_ok=False)

        with open(os.path.join(data_dir, "d.json"), "wb") as f:
            pickle.dump(d, f)
        eventlog_org_df.to_csv(os.path.join(data_dir, "eventlog_org_df.csv"), index=False)
        with open(os.path.join(data_dir, "log_preprocessed.json"), "wb") as f:
            pickle.dump(log_preprocessed, f)
        with open(os.path.join(data_dir, "object_types.pkl"), "wb") as f:
            pickle.dump(d["objectTypes"], f)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------
@app.get("/ocel-process-layout")
def generate_layout(data_dir: str):
    log = load_pickle(data_path(data_dir, "log_preprocessed.json"))

    start_time = time.perf_counter()
    output, mog = MultiObjectGraph.generate_layout_from_log(log=log)
    elapsed_time = time.perf_counter() - start_time
    print(f"[Layout] {data_dir}: {elapsed_time:.4f} seconds")

    # Cache the full layout object so filter requests can reuse it
    os.makedirs(PICKLE_DIR, exist_ok=True)
    pickle_path = os.path.join(PICKLE_DIR, f"{data_dir}_mog.pkl")
    with open(pickle_path, "wb") as f:
        pickle.dump(mog, f)

    return {
        "output": output,
        "pickle_path": pickle_path,
        "layout_time_seconds": elapsed_time,
    }


# -----------------------------------------------------------------------------
# Filtering on a cached layout
# -----------------------------------------------------------------------------
class FilterValueRequest(BaseModel):
    pickle_path: str
    filter_value: float  # 0~100


class FilterEdgesRequest(BaseModel):
    pickle_path: str
    kept_edge_keys: List[str]


class FilterRequest(BaseModel):
    pickle_path: str
    object_types: Optional[List[str]] = None  # None = keep every object type
    filter_value: Optional[float] = None      # 0~100, None = keep every edge


@app.post("/filter-layout-by-value")
def filter_layout_by_value(req: FilterValueRequest):
    mog = load_pickle(req.pickle_path)
    return {"output": mog.recompute_with_filter_value(req.filter_value)}


@app.post("/filter-layout-from-pickle")
def filter_layout_from_pickle(req: FilterEdgesRequest):
    mog = load_pickle(req.pickle_path)
    return {"output": mog.recompute_with_kept_edges(req.kept_edge_keys)}


@app.post("/filter-layout")
def filter_layout(req: FilterRequest):
    """Object-type selection and frequency filter combined, on the cached layout."""
    mog = load_pickle(req.pickle_path)
    try:
        output = mog.recompute_filtered(object_types=req.object_types, filter_value=req.filter_value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"output": output}
