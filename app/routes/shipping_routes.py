import json
from openai import OpenAI
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import OPENAI_API_KEY
from .. import cache

router = APIRouter(prefix="/api", tags=["shipping"])

# ── Static port dataset ───────────────────────────────────────────────────────

PORTS = [
    {
        "code": "USLAX", "name": "Port of Los Angeles / Long Beach",
        "city": "Los Angeles, CA", "region": "West Coast",
        "avg_demurrage_days": 4.2, "congestion_level": "High",
        "annual_teus_millions": 17.5, "avg_processing_days": 3.5,
        "demurrage_rate_usd_per_day": 225,
        "strengths": ["Largest US port by volume", "Best for Asia-Pacific routes", "Strong rail to midwest"],
        "considerations": ["High congestion", "Elevated demurrage costs", "Frequent labor actions"],
        "best_for": ["Consumer electronics", "Apparel", "Auto parts", "Retail goods"],
        "primary_routes": ["China", "Japan", "South Korea", "Vietnam", "Southeast Asia"],
    },
    {
        "code": "USNYC", "name": "Port of New York / New Jersey",
        "city": "New York, NY", "region": "East Coast",
        "avg_demurrage_days": 3.8, "congestion_level": "High",
        "annual_teus_millions": 9.2, "avg_processing_days": 3.2,
        "demurrage_rate_usd_per_day": 210,
        "strengths": ["Largest East Coast port", "Proximity to major distribution centers", "Deep water access"],
        "considerations": ["High operating costs", "Road congestion", "Limited expansion capacity"],
        "best_for": ["Consumer goods", "Apparel", "Food products", "Luxury items"],
        "primary_routes": ["Europe", "Mediterranean", "South America", "West Africa"],
    },
    {
        "code": "USSAV", "name": "Port of Savannah",
        "city": "Savannah, GA", "region": "East Coast",
        "avg_demurrage_days": 2.1, "congestion_level": "Medium",
        "annual_teus_millions": 5.8, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 150,
        "strengths": ["Fastest growing US port", "Low demurrage", "Excellent rail access", "Efficient terminal ops"],
        "considerations": ["Inland congestion during peak season", "Expanding — monitor schedules"],
        "best_for": ["Automotive parts", "Industrial equipment", "Retail goods"],
        "primary_routes": ["Asia", "Europe", "South America"],
    },
    {
        "code": "USSEA", "name": "Port of Seattle / Tacoma (NWSA)",
        "city": "Seattle/Tacoma, WA", "region": "West Coast",
        "avg_demurrage_days": 2.8, "congestion_level": "Medium",
        "annual_teus_millions": 3.9, "avg_processing_days": 2.5,
        "demurrage_rate_usd_per_day": 175,
        "strengths": ["Northern Pacific gateway", "Less congested than LA/LB", "Good Pacific NW distribution"],
        "considerations": ["Smaller throughput capacity", "Winter weather delays"],
        "best_for": ["Agricultural goods", "Technology equipment", "Retail"],
        "primary_routes": ["China", "Japan", "South Korea", "Alaska"],
    },
    {
        "code": "USHOU", "name": "Port of Houston",
        "city": "Houston, TX", "region": "Gulf Coast",
        "avg_demurrage_days": 2.4, "congestion_level": "Low",
        "annual_teus_millions": 3.5, "avg_processing_days": 2.2,
        "demurrage_rate_usd_per_day": 140,
        "strengths": ["Low congestion", "Gulf Coast hub", "Cost-effective operations", "Petrochemical proximity"],
        "considerations": ["Primarily petrochemical focus", "Hurricane season risk (Jun–Nov)"],
        "best_for": ["Energy equipment", "Chemicals", "Steel", "Industrial goods"],
        "primary_routes": ["Mexico", "South America", "Europe", "Middle East"],
    },
    {
        "code": "USMIA", "name": "Port of Miami (PortMiami)",
        "city": "Miami, FL", "region": "Southeast",
        "avg_demurrage_days": 2.6, "congestion_level": "Low",
        "annual_teus_millions": 1.3, "avg_processing_days": 2.3,
        "demurrage_rate_usd_per_day": 160,
        "strengths": ["Latin America gateway", "Low congestion", "Freeport proximity", "Fast customs processing"],
        "considerations": ["Smaller capacity", "Tropical storm season risk"],
        "best_for": ["Perishables", "Luxury goods", "Consumer products", "Fashion"],
        "primary_routes": ["Caribbean", "Central America", "South America"],
    },
    {
        "code": "USCHS", "name": "Port of Charleston",
        "city": "Charleston, SC", "region": "East Coast",
        "avg_demurrage_days": 1.9, "congestion_level": "Low",
        "annual_teus_millions": 2.9, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Lowest avg demurrage on East Coast", "Deep water berths", "Rapidly modernizing", "Very efficient"],
        "considerations": ["Growing fast — monitor capacity windows"],
        "best_for": ["Automotive", "Manufacturing inputs", "Retail"],
        "primary_routes": ["Europe", "Asia", "South America"],
    },
    {
        "code": "USBAL", "name": "Port of Baltimore",
        "city": "Baltimore, MD", "region": "East Coast",
        "avg_demurrage_days": 2.2, "congestion_level": "Low",
        "annual_teus_millions": 1.1, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 145,
        "strengths": ["Direct Midwest access via I-70/I-68", "Auto import specialist", "Low congestion"],
        "considerations": ["Smaller overall container capacity"],
        "best_for": ["Automobiles", "Farm machinery", "Steel products"],
        "primary_routes": ["Europe", "Middle East", "Asia"],
    },
]


# ── Request models ────────────────────────────────────────────────────────────

class ShippingEstimateRequest(BaseModel):
    origin_country: str
    destination_port: str = "Best option"
    weight_kg: float
    volume_cbm: float = 0.0
    product_description: str = ""
    hts_code: str = ""
    cargo_value_usd: float = 0.0


class PortRecommendRequest(BaseModel):
    origin_country: str
    product_description: str = ""
    hts_code: str = ""
    priority: str = "balanced"   # "cost" | "speed" | "low_demurrage" | "balanced"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/ports")
async def list_ports():
    return {"ports": PORTS}


@router.post("/shipping/estimate")
async def shipping_estimate(body: ShippingEstimateRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(503, "Shipping estimates require OPENAI_API_KEY")

    # Check cache first
    ck = cache.cache_key("ship", body.origin_country, body.destination_port or "",
                         body.weight_kg, body.volume_cbm, body.product_description or "",
                         body.cargo_value_usd or 0)
    cached = cache.get("shipping_estimate", ck, ttl=1800)
    if cached is not None:
        print(f"[shipping] Cache hit for estimate")
        return cached

    client = OpenAI(api_key=OPENAI_API_KEY)

    dest_note = f"to {body.destination_port}, USA" if body.destination_port else "to USA"
    product_note = body.product_description or (f"HTS {body.hts_code}" if body.hts_code else "general cargo")
    value_note = f"${body.cargo_value_usd:,.0f}" if body.cargo_value_usd else "undeclared"

    prompt = (
        f"You are a freight shipping expert with current market knowledge (2025).\n\n"
        f"Estimate shipping costs for:\n"
        f"- Route: {body.origin_country} → {dest_note}\n"
        f"- Weight: {body.weight_kg} kg\n"
        f"- Volume: {body.volume_cbm} CBM\n"
        f"- Product: {product_note}\n"
        f"- Cargo value: {value_note}\n\n"
        f"Return ONLY a JSON array of shipping options (no other text):\n"
        f'[{{\n'
        f'  "mode": "Ocean LCL",\n'
        f'  "carrier_examples": ["Maersk", "MSC", "Evergreen"],\n'
        f'  "estimated_cost_usd": 1200,\n'
        f'  "cost_range": "1000–1500",\n'
        f'  "transit_days": 35,\n'
        f'  "notes": "Best for shipments under 15 CBM",\n'
        f'  "recommended": true\n'
        f'}}]\n\n'
        f"Include these modes: Ocean LCL, Ocean FCL 20ft, Ocean FCL 40ft, Air Freight, Express Air.\n"
        f"Set recommended:true on the best value option.\n"
        f"Use realistic 2025 market rates. Include insurance estimates in notes where relevant."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        options = json.loads(raw)
        result = {"options": options, "query": {
            "origin": body.origin_country,
            "destination": body.destination_port,
            "weight_kg": body.weight_kg,
            "volume_cbm": body.volume_cbm,
        }}
        cache.put("shipping_estimate", ck, result)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to generate estimates: {e}")


@router.post("/ports/recommend")
async def recommend_ports(body: PortRecommendRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(503, "Port recommendations require OPENAI_API_KEY")

    # Check cache first
    ck = cache.cache_key("recommend", body.origin_country, body.product_description or "",
                         body.priority or "balanced")
    cached = cache.get("port_recommend", ck, ttl=1800)
    if cached is not None:
        print(f"[ports] Cache hit for recommendation")
        return cached

    client = OpenAI(api_key=OPENAI_API_KEY)

    ports_summary = "\n".join(
        f"- [{p['code']}] {p['name']} | Region: {p['region']} | Avg demurrage: {p['avg_demurrage_days']} days "
        f"| Congestion: {p['congestion_level']} | Routes: {', '.join(p['primary_routes'][:3])}"
        for p in PORTS
    )

    product_note = body.product_description or (f"HTS {body.hts_code}" if body.hts_code else "general cargo")

    prompt = (
        f"You are a port logistics expert.\n\n"
        f"Recommend the best US entry ports for:\n"
        f"- Origin country: {body.origin_country}\n"
        f"- Product: {product_note}\n"
        f"- Priority: {body.priority}\n\n"
        f"Available ports:\n{ports_summary}\n\n"
        f"Return ONLY this JSON (no other text):\n"
        f'{{\n'
        f'  "top_picks": [\n'
        f'    {{"code": "USSAV", "rank": 1, "score": 92, "reason": "why this port fits best", '
        f'"demurrage_advantage": "1.9 days vs 3.5 avg", '
        f'"route_fit": "why the origin lane works", '
        f'"risk_note": "key congestion/customs/weather risk", '
        f'"inland_fit": "distribution or rail/truck advantage"}}\n'
        f'  ],\n'
        f'  "summary": "2-sentence overall recommendation"\n'
        f'}}\n\n'
        f"Return 3 top picks ranked 1–3."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        result = json.loads(raw)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to generate recommendations: {e}")
