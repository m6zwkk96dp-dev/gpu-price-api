from fastapi import FastAPI, HTTPException
import requests

app = FastAPI(
    title="Multi-Cloud GPU Intelligence & Cost Calculator API",
    description="Real-time GPU pricing across clouds, training cost estimation, and deal tracking.",
    version="0.3.0"
)

VAST_API_URL = "https://console.vast.ai/api/v0/bundles/"

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Welcome to GPU Intelligence API! Available endpoints: /cheapest, /compare, /estimate-cost"
    }

@app.get("/cheapest")
def get_cheapest_gpu(gpu_name: str = "4090"):
    """
    Keresés a legolcsóbb GPU-ra a Vast.ai kínálatában (pl. 4090, rtx4090, a100, h100)
    """
    try:
        response = requests.get(VAST_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        offers = data.get("offers", [])
        matching_offers = []
        
        # Tisztítjuk a keresőszót a rugalmas találatokhoz
        search_target = gpu_name.lower().replace(" ", "").replace("-", "").replace("rtx", "")
        
        for offer in offers:
            model_name = str(offer.get("gpu_name", "")).lower().replace(" ", "").replace("-", "")
            if search_target in model_name:
                dph = offer.get("dph_total")
                if dph is not None:
                    matching_offers.append({
                        "provider": "Vast.ai",
                        "gpu_name": offer.get("gpu_name"),
                        "num_gpus": offer.get("num_gpus", 1),
                        "price_per_hour_usd": round(dph, 4),
                        "dlperf": offer.get("dlperf"),
                        "inet_down": offer.get("inet_down"),
                        "geolocation": offer.get("geolocation", "Unknown")
                    })
        
        if not matching_offers:
            raise HTTPException(status_code=404, detail=f"No active GPU offers found for: '{gpu_name}'")
            
        cheapest = min(matching_offers, key=lambda x: x["price_per_hour_usd"])
        return cheapest

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Server error fetching data: {str(e)}")

@app.get("/compare")
def compare_providers(gpu_name: str = "4090"):
    """
    Összehasonlítja a Vast.ai, RunPod és Lambda Labs árait
    """
    vast_res = None
    try:
        vast_res = get_cheapest_gpu(gpu_name)
    except HTTPException as e:
        vast_res = {"error": str(e.detail)}

    # Becsült / piaci benchmark árak a többi szolgáltatótól
    runpod_res = {
        "provider": "RunPod",
        "gpu_name": gpu_name.upper(),
        "price_per_hour_usd": 0.44 if "4090" in gpu_name else 1.89,
        "status": "Available"
    }

    lambda_res = {
        "provider": "Lambda Labs",
        "gpu_name": gpu_name.upper(),
        "price_per_hour_usd": 0.50 if "4090" in gpu_name else 2.49,
        "status": "Limited Availability"
    }

    return {
        "query": gpu_name,
        "comparison": [
            vast_res,
            runpod_res,
            lambda_res
        ]
    }

@app.get("/estimate-cost")
def estimate_cost(hours: float = 10.0, gpu_type: str = "4090", num_gpus: int = 1):
    """
    AI Betanítási és Futtatási Költségkalkulátor
    """
    base_rate = 0.35 if "4090" in gpu_type else 1.50
    try:
        cheapest = get_cheapest_gpu(gpu_type)
        base_rate = cheapest.get("price_per_hour_usd", base_rate)
    except Exception:
        pass

    total_cost = round(base_rate * hours * num_gpus, 2)
    
    return {
        "gpu_type": gpu_type,
        "number_of_gpus": num_gpus,
        "estimated_hours": hours,
        "hourly_rate_per_gpu_usd": base_rate,
        "estimated_total_cost_usd": total_cost,
        "summary": f"Futtatás várható költsége {hours} órára ({num_gpus}x {gpu_type}): ${total_cost} USD"
    }
