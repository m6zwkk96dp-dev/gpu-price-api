import time
from threading import Lock

import requests
import urllib3
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

API_URL = "https://cloud.vast.ai/api/v0/bundles/"
CACHE_TTL_SECONDS = 60

app = FastAPI(title="Vast.ai GPU Pricing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache: dict = {"data": None, "expires_at": 0.0}
_cache_lock = Lock()


class GpuOffer(BaseModel):
    gpu_model: str
    price_per_hour_usd: float
    available_units: int


def _fetch_vast_ai_bundles() -> requests.Response:
    verify: bool | str = True
    try:
        import certifi

        verify = certifi.where()
    except ImportError:
        pass

    try:
        return requests.get(API_URL, timeout=30, verify=verify)
    except requests.exceptions.SSLError:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return requests.get(API_URL, timeout=30, verify=False)


def fetch_cheapest_gpus(limit: int = 5) -> list[GpuOffer]:
    response = _fetch_vast_ai_bundles()
    response.raise_for_status()

    offers = response.json().get("offers", [])
    available = [offer for offer in offers if offer.get("rentable")]
    available.sort(key=lambda offer: offer.get("dph_total", float("inf")))

    return [
        GpuOffer(
            gpu_model=offer.get("gpu_name", "Unknown"),
            price_per_hour_usd=round(offer.get("dph_total", 0), 6),
            available_units=offer.get("num_gpus", 0),
        )
        for offer in available[:limit]
    ]


def get_cached_cheapest_gpus(limit: int = 5) -> list[GpuOffer]:
    now = time.time()

    with _cache_lock:
        if _cache["data"] is not None and now < _cache["expires_at"]:
            return _cache["data"][:limit]

    try:
        data = fetch_cheapest_gpus(limit=limit)
    except requests.exceptions.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching GPU market data: {exc}",
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error parsing GPU market data: {exc}",
        ) from exc

    with _cache_lock:
        _cache["data"] = data
        _cache["expires_at"] = time.time() + CACHE_TTL_SECONDS

    return data


@app.get("/v1/gpus/cheapest", response_model=list[GpuOffer])
def get_cheapest_gpus() -> list[GpuOffer]:
    return get_cached_cheapest_gpus()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
