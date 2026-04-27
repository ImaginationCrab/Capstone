import json
from openai import OpenAI
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from ..config import OPENAI_API_KEY
from .. import cache

router = APIRouter(prefix="/api", tags=["shipping"])

# ── Static port dataset ───────────────────────────────────────────────────────

PORTS = [
    {
        "code": "USLAX", "name": "Port of Los Angeles",
        "city": "Los Angeles, CA", "region": "US West Coast", "country": "United States",
        "latitude": 33.74, "longitude": -118.27,
        "avg_demurrage_days": 4.2, "congestion_level": "High",
        "annual_teus_millions": 9.3, "avg_processing_days": 3.5,
        "demurrage_rate_usd_per_day": 225,
        "strengths": ["Largest US container gateway", "Best for Asia-Pacific routes", "Strong rail to Midwest"],
        "considerations": ["High congestion", "Elevated demurrage costs", "Frequent labor actions"],
        "best_for": ["Consumer electronics", "Apparel", "Auto parts", "Retail goods"],
        "primary_routes": ["China", "Japan", "South Korea", "Vietnam", "Southeast Asia"],
    },
    {
        "code": "USLGB", "name": "Port of Long Beach",
        "city": "Long Beach, CA", "region": "US West Coast", "country": "United States",
        "latitude": 33.76, "longitude": -118.20,
        "avg_demurrage_days": 3.9, "congestion_level": "High",
        "annual_teus_millions": 8.0, "avg_processing_days": 3.2,
        "demurrage_rate_usd_per_day": 220,
        "strengths": ["Major trans-Pacific gateway", "Green terminal investments", "Dense drayage and rail network"],
        "considerations": ["Shares Southern California congestion exposure", "Peak-season chassis pressure"],
        "best_for": ["Retail goods", "Furniture", "Electronics", "Consumer products"],
        "primary_routes": ["China", "Vietnam", "Taiwan", "South Korea", "Southeast Asia"],
    },
    {
        "code": "USOAK", "name": "Port of Oakland",
        "city": "Oakland, CA", "region": "US West Coast", "country": "United States",
        "latitude": 37.80, "longitude": -122.32,
        "avg_demurrage_days": 2.7, "congestion_level": "Medium",
        "annual_teus_millions": 2.3, "avg_processing_days": 2.4,
        "demurrage_rate_usd_per_day": 165,
        "strengths": ["Northern California import gateway", "Strong export balance", "Good Bay Area access"],
        "considerations": ["Less carrier frequency than LA/LB", "Local road congestion"],
        "best_for": ["Food products", "Wine and beverages", "Technology equipment", "Retail"],
        "primary_routes": ["China", "Japan", "South Korea", "Australia"],
    },
    {
        "code": "USNYC", "name": "Port of New York / New Jersey",
        "city": "New York, NY", "region": "US East Coast", "country": "United States",
        "latitude": 40.67, "longitude": -74.05,
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
        "city": "Savannah, GA", "region": "US East Coast", "country": "United States",
        "latitude": 32.08, "longitude": -81.09,
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
        "city": "Seattle/Tacoma, WA", "region": "US West Coast", "country": "United States",
        "latitude": 47.37, "longitude": -122.40,
        "avg_demurrage_days": 2.8, "congestion_level": "Medium",
        "annual_teus_millions": 3.9, "avg_processing_days": 2.5,
        "demurrage_rate_usd_per_day": 175,
        "strengths": ["Northern Pacific gateway", "Less congested than LA/LB", "Good Pacific NW distribution"],
        "considerations": ["Smaller throughput capacity", "Winter weather delays"],
        "best_for": ["Agricultural goods", "Technology equipment", "Retail"],
        "primary_routes": ["China", "Japan", "South Korea", "Alaska"],
    },
    {
        "code": "USORF", "name": "Port of Virginia / Norfolk",
        "city": "Norfolk, VA", "region": "US East Coast", "country": "United States",
        "latitude": 36.85, "longitude": -76.29,
        "avg_demurrage_days": 2.0, "congestion_level": "Low",
        "annual_teus_millions": 3.7, "avg_processing_days": 1.9,
        "demurrage_rate_usd_per_day": 145,
        "strengths": ["Deep harbor", "Strong rail to Midwest", "Efficient automated terminals"],
        "considerations": ["Mid-Atlantic routing may add inland miles for Northeast cargo"],
        "best_for": ["Retail", "Furniture", "Manufacturing inputs", "Agricultural exports"],
        "primary_routes": ["Europe", "Asia", "Mediterranean", "South America"],
    },
    {
        "code": "USHOU", "name": "Port of Houston",
        "city": "Houston, TX", "region": "US Gulf Coast", "country": "United States",
        "latitude": 29.73, "longitude": -95.26,
        "avg_demurrage_days": 2.4, "congestion_level": "Low",
        "annual_teus_millions": 3.5, "avg_processing_days": 2.2,
        "demurrage_rate_usd_per_day": 140,
        "strengths": ["Low congestion", "Gulf Coast hub", "Cost-effective operations", "Petrochemical proximity"],
        "considerations": ["Primarily petrochemical focus", "Hurricane season risk (Jun–Nov)"],
        "best_for": ["Energy equipment", "Chemicals", "Steel", "Industrial goods"],
        "primary_routes": ["Mexico", "South America", "Europe", "Middle East"],
    },
    {
        "code": "USMSY", "name": "Port of New Orleans",
        "city": "New Orleans, LA", "region": "US Gulf Coast", "country": "United States",
        "latitude": 29.95, "longitude": -90.06,
        "avg_demurrage_days": 2.3, "congestion_level": "Low",
        "annual_teus_millions": 0.6, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 125,
        "strengths": ["Mississippi River access", "Breakbulk and project cargo experience", "Gulf distribution reach"],
        "considerations": ["Lower container frequency", "River weather and draft variability"],
        "best_for": ["Breakbulk", "Agricultural goods", "Steel", "Project cargo"],
        "primary_routes": ["Caribbean", "Central America", "South America", "Europe"],
    },
    {
        "code": "USMOB", "name": "Port of Mobile",
        "city": "Mobile, AL", "region": "US Gulf Coast", "country": "United States",
        "latitude": 30.69, "longitude": -88.04,
        "avg_demurrage_days": 1.8, "congestion_level": "Low",
        "annual_teus_millions": 0.6, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 120,
        "strengths": ["Low congestion", "Good Southeast rail connections", "Growing container capacity"],
        "considerations": ["Smaller carrier network than Houston or Savannah"],
        "best_for": ["Automotive", "Forest products", "Manufacturing inputs", "Retail"],
        "primary_routes": ["Central America", "Europe", "Asia", "Mexico"],
    },
    {
        "code": "USMIA", "name": "Port of Miami (PortMiami)",
        "city": "Miami, FL", "region": "US Southeast", "country": "United States",
        "latitude": 25.78, "longitude": -80.16,
        "avg_demurrage_days": 2.6, "congestion_level": "Low",
        "annual_teus_millions": 1.3, "avg_processing_days": 2.3,
        "demurrage_rate_usd_per_day": 160,
        "strengths": ["Latin America gateway", "Low congestion", "Freeport proximity", "Fast customs processing"],
        "considerations": ["Smaller capacity", "Tropical storm season risk"],
        "best_for": ["Perishables", "Luxury goods", "Consumer products", "Fashion"],
        "primary_routes": ["Caribbean", "Central America", "South America"],
    },
    {
        "code": "USPEF", "name": "Port Everglades",
        "city": "Fort Lauderdale, FL", "region": "US Southeast", "country": "United States",
        "latitude": 26.09, "longitude": -80.12,
        "avg_demurrage_days": 2.4, "congestion_level": "Low",
        "annual_teus_millions": 1.0, "avg_processing_days": 2.1,
        "demurrage_rate_usd_per_day": 150,
        "strengths": ["South Florida distribution", "Refrigerated cargo capacity", "Latin America and Caribbean links"],
        "considerations": ["Smaller capacity than major East Coast gateways"],
        "best_for": ["Perishables", "Beverages", "Apparel", "Consumer goods"],
        "primary_routes": ["Caribbean", "Central America", "South America"],
    },
    {
        "code": "USCHS", "name": "Port of Charleston",
        "city": "Charleston, SC", "region": "US East Coast", "country": "United States",
        "latitude": 32.78, "longitude": -79.93,
        "avg_demurrage_days": 1.9, "congestion_level": "Low",
        "annual_teus_millions": 2.9, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Lowest avg demurrage on East Coast", "Deep water berths", "Rapidly modernizing", "Very efficient"],
        "considerations": ["Growing fast — monitor capacity windows"],
        "best_for": ["Automotive", "Manufacturing inputs", "Retail"],
        "primary_routes": ["Europe", "Asia", "South America"],
    },
    {
        "code": "USJAX", "name": "Jacksonville Port Authority",
        "city": "Jacksonville, FL", "region": "US Southeast", "country": "United States",
        "latitude": 30.34, "longitude": -81.55,
        "avg_demurrage_days": 2.0, "congestion_level": "Low",
        "annual_teus_millions": 1.4, "avg_processing_days": 1.9,
        "demurrage_rate_usd_per_day": 130,
        "strengths": ["Auto and ro-ro strength", "Puerto Rico trade lane", "Southeast highway access"],
        "considerations": ["Less direct Asia service than Savannah or Charleston"],
        "best_for": ["Automobiles", "Retail", "Food products", "Project cargo"],
        "primary_routes": ["Puerto Rico", "Caribbean", "South America", "Europe"],
    },
    {
        "code": "USBAL", "name": "Port of Baltimore",
        "city": "Baltimore, MD", "region": "US East Coast", "country": "United States",
        "latitude": 39.27, "longitude": -76.58,
        "avg_demurrage_days": 2.2, "congestion_level": "Low",
        "annual_teus_millions": 1.1, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 145,
        "strengths": ["Direct Midwest access via I-70/I-68", "Auto import specialist", "Low congestion"],
        "considerations": ["Smaller overall container capacity"],
        "best_for": ["Automobiles", "Farm machinery", "Steel products"],
        "primary_routes": ["Europe", "Middle East", "Asia"],
    },
    {
        "code": "USPHL", "name": "Port of Philadelphia",
        "city": "Philadelphia, PA", "region": "US East Coast", "country": "United States",
        "latitude": 39.90, "longitude": -75.14,
        "avg_demurrage_days": 2.1, "congestion_level": "Low",
        "annual_teus_millions": 0.7, "avg_processing_days": 1.9,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Cold-chain specialists", "Northeast food distribution", "Lower congestion"],
        "considerations": ["Niche container network", "Limited direct Asia frequency"],
        "best_for": ["Fresh fruit", "Meat", "Seafood", "Food and beverage"],
        "primary_routes": ["South America", "Europe", "Mediterranean", "Caribbean"],
    },
    {
        "code": "CAVAN", "name": "Port of Vancouver",
        "city": "Vancouver, BC", "region": "North America West Coast", "country": "Canada",
        "latitude": 49.29, "longitude": -123.12,
        "avg_demurrage_days": 3.0, "congestion_level": "Medium",
        "annual_teus_millions": 3.7, "avg_processing_days": 2.6,
        "demurrage_rate_usd_per_day": 170,
        "strengths": ["Canada's largest port", "Pacific gateway", "Strong rail to Canadian and US interiors"],
        "considerations": ["Rail disruption risk", "Weather and labor sensitivity"],
        "best_for": ["Retail", "Forest products", "Agricultural goods", "Industrial inputs"],
        "primary_routes": ["China", "Japan", "South Korea", "Southeast Asia"],
    },
    {
        "code": "MXZLO", "name": "Port of Manzanillo",
        "city": "Manzanillo, Colima", "region": "North America Pacific", "country": "Mexico",
        "latitude": 19.05, "longitude": -104.32,
        "avg_demurrage_days": 2.7, "congestion_level": "Medium",
        "annual_teus_millions": 3.7, "avg_processing_days": 2.5,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Mexico's leading container port", "Asia-Mexico gateway", "Central Mexico rail access"],
        "considerations": ["Customs holds can vary", "Peak-period yard pressure"],
        "best_for": ["Automotive parts", "Retail", "Electronics", "Industrial goods"],
        "primary_routes": ["China", "Japan", "South Korea", "US West Coast"],
    },
    {
        "code": "BRSSZ", "name": "Port of Santos",
        "city": "Santos, Sao Paulo", "region": "South America Atlantic", "country": "Brazil",
        "latitude": -23.96, "longitude": -46.30,
        "avg_demurrage_days": 3.2, "congestion_level": "Medium",
        "annual_teus_millions": 4.8, "avg_processing_days": 3.0,
        "demurrage_rate_usd_per_day": 150,
        "strengths": ["Brazil's primary container gateway", "Sao Paulo industrial access", "Strong reefer trade"],
        "considerations": ["Customs complexity", "Inland road congestion"],
        "best_for": ["Coffee", "Meat", "Industrial goods", "Consumer products"],
        "primary_routes": ["Europe", "US East Coast", "Asia", "South America"],
    },
    {
        "code": "NLRTM", "name": "Port of Rotterdam",
        "city": "Rotterdam", "region": "Northern Europe", "country": "Netherlands",
        "latitude": 51.95, "longitude": 4.14,
        "avg_demurrage_days": 2.5, "congestion_level": "Medium",
        "annual_teus_millions": 13.4, "avg_processing_days": 2.1,
        "demurrage_rate_usd_per_day": 185,
        "strengths": ["Europe's largest port", "Deepwater mega-ship access", "Rhine inland network"],
        "considerations": ["High labor and storage costs", "Weather and barge congestion risk"],
        "best_for": ["Chemicals", "Consumer goods", "Machinery", "Food products"],
        "primary_routes": ["Asia", "North America", "Mediterranean", "Africa"],
    },
    {
        "code": "BEANR", "name": "Port of Antwerp-Bruges",
        "city": "Antwerp/Zeebrugge", "region": "Northern Europe", "country": "Belgium",
        "latitude": 51.27, "longitude": 4.35,
        "avg_demurrage_days": 2.6, "congestion_level": "Medium",
        "annual_teus_millions": 13.5, "avg_processing_days": 2.2,
        "demurrage_rate_usd_per_day": 180,
        "strengths": ["Major European chemical and container hub", "Dense inland barge and rail options", "Good Benelux access"],
        "considerations": ["Tidal river access", "Peak yard congestion"],
        "best_for": ["Chemicals", "Pharmaceuticals", "Machinery", "Retail"],
        "primary_routes": ["Asia", "North America", "Africa", "Mediterranean"],
    },
    {
        "code": "DEHAM", "name": "Port of Hamburg",
        "city": "Hamburg", "region": "Northern Europe", "country": "Germany",
        "latitude": 53.55, "longitude": 9.99,
        "avg_demurrage_days": 2.4, "congestion_level": "Medium",
        "annual_teus_millions": 7.7, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 175,
        "strengths": ["Central and Eastern Europe reach", "Strong rail share", "High-value cargo expertise"],
        "considerations": ["Elbe draft constraints", "Labor disruption risk"],
        "best_for": ["Machinery", "Automotive parts", "Electronics", "Consumer goods"],
        "primary_routes": ["Asia", "North America", "Baltic", "Scandinavia"],
    },
    {
        "code": "GBFXT", "name": "Port of Felixstowe",
        "city": "Felixstowe", "region": "Northern Europe", "country": "United Kingdom",
        "latitude": 51.96, "longitude": 1.35,
        "avg_demurrage_days": 2.3, "congestion_level": "Medium",
        "annual_teus_millions": 4.0, "avg_processing_days": 2.1,
        "demurrage_rate_usd_per_day": 170,
        "strengths": ["UK's largest container port", "Direct Asia and Europe services", "Rail to Midlands"],
        "considerations": ["Peak-season road and rail constraints", "Customs documentation sensitivity"],
        "best_for": ["Retail", "Apparel", "Electronics", "Food products"],
        "primary_routes": ["Asia", "Northern Europe", "Mediterranean", "North America"],
    },
    {
        "code": "ESVLC", "name": "Port of Valencia",
        "city": "Valencia", "region": "Mediterranean Europe", "country": "Spain",
        "latitude": 39.45, "longitude": -0.32,
        "avg_demurrage_days": 2.2, "congestion_level": "Low",
        "annual_teus_millions": 5.1, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 145,
        "strengths": ["Western Mediterranean hub", "Good Iberian access", "Strong reefer handling"],
        "considerations": ["Transshipment delays during peak periods"],
        "best_for": ["Food products", "Tiles and ceramics", "Retail", "Automotive parts"],
        "primary_routes": ["Mediterranean", "North Africa", "Asia", "North America"],
    },
    {
        "code": "MAPTM", "name": "Tanger Med Port",
        "city": "Tangier", "region": "North Africa", "country": "Morocco",
        "latitude": 35.89, "longitude": -5.50,
        "avg_demurrage_days": 1.9, "congestion_level": "Low",
        "annual_teus_millions": 8.6, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 120,
        "strengths": ["Strategic transshipment hub", "Europe-Africa connector", "Competitive costs"],
        "considerations": ["Often used as transshipment rather than final destination"],
        "best_for": ["Transshipment", "Automotive", "Apparel", "Retail"],
        "primary_routes": ["Europe", "West Africa", "Mediterranean", "North America"],
    },
    {
        "code": "AEJEA", "name": "Jebel Ali Port",
        "city": "Dubai", "region": "Middle East", "country": "United Arab Emirates",
        "latitude": 25.01, "longitude": 55.06,
        "avg_demurrage_days": 2.0, "congestion_level": "Low",
        "annual_teus_millions": 14.5, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 150,
        "strengths": ["Middle East mega hub", "Free zone integration", "Excellent transshipment network"],
        "considerations": ["Regional geopolitics and routing disruption risk"],
        "best_for": ["Re-exports", "Electronics", "Consumer goods", "Industrial equipment"],
        "primary_routes": ["Asia", "Europe", "Africa", "Middle East"],
    },
    {
        "code": "INNSA", "name": "Jawaharlal Nehru Port / Nhava Sheva",
        "city": "Mumbai", "region": "South Asia", "country": "India",
        "latitude": 18.95, "longitude": 72.95,
        "avg_demurrage_days": 3.3, "congestion_level": "Medium",
        "annual_teus_millions": 6.0, "avg_processing_days": 3.0,
        "demurrage_rate_usd_per_day": 120,
        "strengths": ["India's largest container gateway", "Mumbai industrial region", "Growing rail connectivity"],
        "considerations": ["Customs/documentation variability", "Monsoon disruption risk"],
        "best_for": ["Textiles", "Pharmaceuticals", "Machinery", "Consumer goods"],
        "primary_routes": ["Middle East", "Europe", "US East Coast", "Southeast Asia"],
    },
    {
        "code": "SGSIN", "name": "Port of Singapore",
        "city": "Singapore", "region": "Southeast Asia", "country": "Singapore",
        "latitude": 1.26, "longitude": 103.82,
        "avg_demurrage_days": 1.8, "congestion_level": "Low",
        "annual_teus_millions": 39.0, "avg_processing_days": 1.5,
        "demurrage_rate_usd_per_day": 165,
        "strengths": ["Global transshipment leader", "Excellent schedule reliability", "Deep carrier network"],
        "considerations": ["Premium storage costs", "Mostly a hub rather than final market"],
        "best_for": ["Transshipment", "Electronics", "Pharmaceuticals", "High-value cargo"],
        "primary_routes": ["Asia", "Europe", "Middle East", "Oceania"],
    },
    {
        "code": "MYPKG", "name": "Port Klang",
        "city": "Klang", "region": "Southeast Asia", "country": "Malaysia",
        "latitude": 3.00, "longitude": 101.40,
        "avg_demurrage_days": 2.1, "congestion_level": "Medium",
        "annual_teus_millions": 14.1, "avg_processing_days": 1.9,
        "demurrage_rate_usd_per_day": 110,
        "strengths": ["Major Southeast Asia hub", "Lower cost than Singapore", "Malaysia manufacturing access"],
        "considerations": ["Transshipment dwell variability"],
        "best_for": ["Electronics", "Rubber products", "Furniture", "Retail"],
        "primary_routes": ["Asia", "Europe", "Middle East", "Oceania"],
    },
    {
        "code": "THLCH", "name": "Laem Chabang Port",
        "city": "Chonburi", "region": "Southeast Asia", "country": "Thailand",
        "latitude": 13.08, "longitude": 100.89,
        "avg_demurrage_days": 2.3, "congestion_level": "Medium",
        "annual_teus_millions": 8.7, "avg_processing_days": 2.1,
        "demurrage_rate_usd_per_day": 105,
        "strengths": ["Thailand's main deep-sea port", "Eastern Economic Corridor access", "Auto export strength"],
        "considerations": ["Inland trucking congestion near Bangkok"],
        "best_for": ["Automotive", "Electronics", "Food products", "Rubber goods"],
        "primary_routes": ["Asia", "North America", "Europe", "Oceania"],
    },
    {
        "code": "CNSHA", "name": "Port of Shanghai",
        "city": "Shanghai", "region": "East Asia", "country": "China",
        "latitude": 31.23, "longitude": 121.50,
        "avg_demurrage_days": 2.6, "congestion_level": "Medium",
        "annual_teus_millions": 49.0, "avg_processing_days": 2.2,
        "demurrage_rate_usd_per_day": 145,
        "strengths": ["World-scale container volume", "Yangtze River Delta manufacturing", "Dense carrier coverage"],
        "considerations": ["Weather and blank-sailing sensitivity", "Peak-season yard pressure"],
        "best_for": ["Electronics", "Machinery", "Consumer goods", "Industrial inputs"],
        "primary_routes": ["North America", "Europe", "Southeast Asia", "Middle East"],
    },
    {
        "code": "CNNGB", "name": "Port of Ningbo-Zhoushan",
        "city": "Ningbo/Zhoushan", "region": "East Asia", "country": "China",
        "latitude": 29.87, "longitude": 121.55,
        "avg_demurrage_days": 2.4, "congestion_level": "Medium",
        "annual_teus_millions": 35.0, "avg_processing_days": 2.0,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Major China export gateway", "Deepwater capacity", "Strong hinterland manufacturing base"],
        "considerations": ["Typhoon-season disruption risk"],
        "best_for": ["Machinery", "Tools", "Furniture", "Consumer goods"],
        "primary_routes": ["North America", "Europe", "Southeast Asia", "Middle East"],
    },
    {
        "code": "CNSZX", "name": "Port of Shenzhen",
        "city": "Shenzhen", "region": "East Asia", "country": "China",
        "latitude": 22.54, "longitude": 114.05,
        "avg_demurrage_days": 2.5, "congestion_level": "Medium",
        "annual_teus_millions": 30.0, "avg_processing_days": 2.1,
        "demurrage_rate_usd_per_day": 140,
        "strengths": ["Pearl River Delta manufacturing access", "Electronics supply chain depth", "Multiple terminal options"],
        "considerations": ["Cross-border Hong Kong routing complexity", "Peak export congestion"],
        "best_for": ["Electronics", "Consumer tech", "Toys", "Apparel"],
        "primary_routes": ["North America", "Europe", "Southeast Asia", "Oceania"],
    },
    {
        "code": "HKHKG", "name": "Port of Hong Kong",
        "city": "Hong Kong", "region": "East Asia", "country": "Hong Kong",
        "latitude": 22.31, "longitude": 114.17,
        "avg_demurrage_days": 2.0, "congestion_level": "Low",
        "annual_teus_millions": 14.3, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 155,
        "strengths": ["Flexible feeder network", "High-value cargo handling", "South China logistics services"],
        "considerations": ["Lost direct share to Shenzhen and Guangzhou", "Premium terminal costs"],
        "best_for": ["High-value goods", "Electronics", "Air-sea cargo", "Re-exports"],
        "primary_routes": ["South China", "Southeast Asia", "North America", "Europe"],
    },
    {
        "code": "KRPUS", "name": "Port of Busan",
        "city": "Busan", "region": "East Asia", "country": "South Korea",
        "latitude": 35.10, "longitude": 129.04,
        "avg_demurrage_days": 2.0, "congestion_level": "Low",
        "annual_teus_millions": 23.0, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 135,
        "strengths": ["Northeast Asia transshipment hub", "Reliable terminal productivity", "Strong Japan feeder links"],
        "considerations": ["Weather disruption during typhoon season"],
        "best_for": ["Transshipment", "Automotive parts", "Electronics", "Machinery"],
        "primary_routes": ["North America", "Japan", "China", "Europe"],
    },
    {
        "code": "JPYOK", "name": "Port of Yokohama",
        "city": "Yokohama", "region": "East Asia", "country": "Japan",
        "latitude": 35.45, "longitude": 139.64,
        "avg_demurrage_days": 1.9, "congestion_level": "Low",
        "annual_teus_millions": 3.0, "avg_processing_days": 1.8,
        "demurrage_rate_usd_per_day": 150,
        "strengths": ["Tokyo metro access", "Reliable customs and terminal operations", "Automotive supply chain strength"],
        "considerations": ["Higher local handling costs"],
        "best_for": ["Automotive parts", "Machinery", "Electronics", "High-value cargo"],
        "primary_routes": ["North America", "Asia", "Europe", "Oceania"],
    },
    {
        "code": "TWKHH", "name": "Port of Kaohsiung",
        "city": "Kaohsiung", "region": "East Asia", "country": "Taiwan",
        "latitude": 22.61, "longitude": 120.29,
        "avg_demurrage_days": 1.9, "congestion_level": "Low",
        "annual_teus_millions": 9.6, "avg_processing_days": 1.7,
        "demurrage_rate_usd_per_day": 125,
        "strengths": ["Taiwan's main container hub", "Semiconductor and electronics access", "Strong feeder services"],
        "considerations": ["Typhoon exposure", "Geopolitical routing risk"],
        "best_for": ["Electronics", "Semiconductors", "Machinery", "Bicycles"],
        "primary_routes": ["North America", "China", "Southeast Asia", "Europe"],
    },
    {
        "code": "AUSYD", "name": "Port Botany",
        "city": "Sydney", "region": "Oceania", "country": "Australia",
        "latitude": -33.97, "longitude": 151.22,
        "avg_demurrage_days": 2.8, "congestion_level": "Medium",
        "annual_teus_millions": 2.7, "avg_processing_days": 2.4,
        "demurrage_rate_usd_per_day": 180,
        "strengths": ["Sydney consumer market access", "Reefer and retail strength", "Established customs infrastructure"],
        "considerations": ["Higher terminal and inland costs", "Urban trucking constraints"],
        "best_for": ["Retail", "Food products", "Pharmaceuticals", "Consumer goods"],
        "primary_routes": ["Asia", "North America", "New Zealand", "Europe"],
    },
    {
        "code": "ZADUR", "name": "Port of Durban",
        "city": "Durban", "region": "Sub-Saharan Africa", "country": "South Africa",
        "latitude": -29.88, "longitude": 31.05,
        "avg_demurrage_days": 4.0, "congestion_level": "High",
        "annual_teus_millions": 2.6, "avg_processing_days": 3.8,
        "demurrage_rate_usd_per_day": 130,
        "strengths": ["Southern Africa's key container gateway", "Regional inland access", "Automotive and commodity links"],
        "considerations": ["Congestion and equipment constraints", "Labor and weather disruption risk"],
        "best_for": ["Automotive", "Agricultural goods", "Retail", "Industrial cargo"],
        "primary_routes": ["Asia", "Europe", "Middle East", "Africa"],
    },
]


# ── Request models ────────────────────────────────────────────────────────────

class ShippingEstimateRequest(BaseModel):
    origin_country: str
    destination_port: str = "Best option"
    destination_country: str = "United States"
    destination_zip: str = ""
    weight_kg: float
    volume_cbm: float = 0.0
    product_description: str = ""
    hts_code: str = ""
    cargo_value_usd: float = 0.0


class PortRecommendRequest(BaseModel):
    origin_country: str
    destination_country: str = "United States"
    product_description: str = ""
    hts_code: str = ""
    priority: str = "balanced"   # "cost" | "speed" | "low_demurrage" | "balanced"


# ── Trade lane modeling helpers ───────────────────────────────────────────────

def _chapter_from_code(hts_code: str) -> int:
    digits = "".join(ch for ch in (hts_code or "") if ch.isdigit())
    if len(digits) < 2:
        return 0
    try:
        return int(digits[:2])
    except ValueError:
        return 0


def _trade_profile(chapter: int) -> dict:
    if 1 <= chapter <= 24:
        return {
            "category": "Food, agriculture, and perishables",
            "origin_regions": ["Latin America", "Europe", "Asia"],
            "cargo_terms": ["Food products", "Perishables", "Agricultural goods", "Meat", "Seafood", "Beverages"],
            "preferred_ports": ["USMIA", "USPEF", "USPHL", "USNYC", "USOAK", "USSEA", "USHOU"],
            "route_bias": ["South America", "Central America", "Caribbean", "Europe"],
        }
    if 25 <= chapter <= 27:
        return {
            "category": "Minerals, fuels, and energy inputs",
            "origin_regions": ["Middle East", "South America", "Canada", "Europe"],
            "cargo_terms": ["Energy equipment", "Chemicals", "Steel", "Industrial goods", "Breakbulk"],
            "preferred_ports": ["USHOU", "USMSY", "USMOB", "USBAL", "NLRTM", "AEJEA"],
            "route_bias": ["Middle East", "South America", "Europe", "Mexico"],
        }
    if 28 <= chapter <= 40:
        return {
            "category": "Chemicals, plastics, rubber, and pharma inputs",
            "origin_regions": ["Europe", "Asia", "Middle East"],
            "cargo_terms": ["Chemicals", "Pharmaceuticals", "Rubber products", "Industrial inputs"],
            "preferred_ports": ["USHOU", "USNYC", "USPHL", "USCHS", "NLRTM", "BEANR", "AEJEA"],
            "route_bias": ["Europe", "Asia", "Middle East"],
        }
    if 41 <= chapter <= 43 or 50 <= chapter <= 67:
        return {
            "category": "Textiles, apparel, footwear, and leather goods",
            "origin_regions": ["China", "Vietnam", "Southeast Asia", "South Asia"],
            "cargo_terms": ["Apparel", "Fashion", "Retail goods", "Consumer products", "Textiles"],
            "preferred_ports": ["USLAX", "USLGB", "USNYC", "USSAV", "USCHS", "USMIA", "INNSA", "CNSZX"],
            "route_bias": ["China", "Vietnam", "Southeast Asia", "South Asia"],
        }
    if 44 <= chapter <= 49:
        return {
            "category": "Wood, paper, and forest products",
            "origin_regions": ["Canada", "Asia", "South America", "Europe"],
            "cargo_terms": ["Forest products", "Furniture", "Agricultural goods", "Retail"],
            "preferred_ports": ["CAVAN", "USSEA", "USOAK", "USSAV", "USCHS", "BRSSZ"],
            "route_bias": ["Canada", "Asia", "South America", "Europe"],
        }
    if 68 <= chapter <= 71:
        return {
            "category": "Stone, glass, ceramics, metals, and jewelry",
            "origin_regions": ["Europe", "Asia", "South America"],
            "cargo_terms": ["Tiles and ceramics", "Luxury goods", "Machinery", "Consumer goods"],
            "preferred_ports": ["USNYC", "USSAV", "USLAX", "USLGB", "ESVLC", "DEHAM"],
            "route_bias": ["Europe", "Asia", "Mediterranean"],
        }
    if 72 <= chapter <= 83:
        return {
            "category": "Base metals and metal articles",
            "origin_regions": ["Europe", "Asia", "South America", "Middle East"],
            "cargo_terms": ["Steel", "Industrial goods", "Manufacturing inputs", "Farm machinery", "Breakbulk"],
            "preferred_ports": ["USHOU", "USBAL", "USORF", "USMSY", "USSAV", "USCHS", "DEHAM"],
            "route_bias": ["Europe", "Asia", "Middle East", "South America"],
        }
    if 84 <= chapter <= 85 or 90 <= chapter <= 92:
        return {
            "category": "Machinery, electronics, and precision equipment",
            "origin_regions": ["China", "Japan", "South Korea", "Taiwan", "Southeast Asia"],
            "cargo_terms": ["Electronics", "Technology equipment", "Machinery", "Consumer tech", "High-value cargo"],
            "preferred_ports": ["USLAX", "USLGB", "USSEA", "USSAV", "USNYC", "USCHS", "CNSHA", "CNSZX", "KRPUS"],
            "route_bias": ["China", "Japan", "South Korea", "Taiwan", "Southeast Asia"],
        }
    if 86 <= chapter <= 89:
        return {
            "category": "Vehicles, aircraft, vessels, and transport parts",
            "origin_regions": ["Japan", "South Korea", "Europe", "Mexico"],
            "cargo_terms": ["Automotive", "Automobiles", "Auto parts", "Machinery", "Project cargo"],
            "preferred_ports": ["USBAL", "USSAV", "USCHS", "USJAX", "USHOU", "JPYOK", "KRPUS", "DEHAM"],
            "route_bias": ["Japan", "South Korea", "Europe", "Mexico"],
        }
    if 93 <= chapter <= 97:
        return {
            "category": "Furniture, toys, sporting goods, and miscellaneous manufactured goods",
            "origin_regions": ["China", "Southeast Asia", "Europe"],
            "cargo_terms": ["Furniture", "Toys", "Retail goods", "Consumer products", "Apparel"],
            "preferred_ports": ["USLAX", "USLGB", "USSAV", "USNYC", "USCHS", "USOAK", "CNSZX"],
            "route_bias": ["China", "Vietnam", "Southeast Asia", "Europe"],
        }
    return {
        "category": "General containerized cargo",
        "origin_regions": ["Asia", "Europe", "Latin America"],
        "cargo_terms": ["Consumer goods", "Retail", "Industrial goods", "Manufacturing inputs"],
        "preferred_ports": ["USLAX", "USLGB", "USNYC", "USSAV", "USCHS", "USHOU"],
        "route_bias": ["Asia", "Europe", "South America"],
    }


def _port_trade_score(port: dict, profile: dict, destination_country: str) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    if not destination_country or port["country"].lower() == destination_country.lower():
        score += 28
        reasons.append("destination-market gateway")
    elif port["country"] != "United States" and destination_country.lower() != "united states":
        score += 12
        reasons.append("global origin or transshipment hub")

    volume = float(port.get("annual_teus_millions") or 0)
    score += min(volume * 1.25, 24)

    if port["code"] in profile["preferred_ports"]:
        score += 24
        reasons.append("strong fit for this HTS category")

    best_for = " ".join(port.get("best_for", [])).lower()
    matches = [term for term in profile["cargo_terms"] if term.lower() in best_for]
    if matches:
        score += min(len(matches) * 7, 21)
        reasons.append("cargo specialization match")

    routes = [route.lower() for route in port.get("primary_routes", [])]
    route_matches = [route for route in profile["route_bias"] if any(route.lower() in r for r in routes)]
    if route_matches:
        score += min(len(route_matches) * 5, 15)
        reasons.append("common origin-route alignment")

    congestion_penalty = {"Low": 0, "Medium": 4, "High": 8}.get(port.get("congestion_level"), 4)
    score -= congestion_penalty
    score -= min(float(port.get("avg_demurrage_days") or 0) * 1.5, 7)

    return max(score, 1), reasons[:3]


def _modeled_trade_heatmap(hts_code: str, destination_country: str) -> dict:
    chapter = _chapter_from_code(hts_code)
    profile = _trade_profile(chapter)

    scored = []
    for port in PORTS:
        raw_score, reasons = _port_trade_score(port, profile, destination_country or "United States")
        scored.append((raw_score, port, reasons))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:12]
    total = sum(item[0] for item in top) or 1

    ports = []
    for rank, (raw_score, port, reasons) in enumerate(top, start=1):
        share = raw_score / total * 100
        preferred_route = next(
            (route for route in profile["route_bias"] if route in port.get("primary_routes", [])),
            port.get("primary_routes", ["General cargo"])[0],
        )
        ports.append({
            "rank": rank,
            "score": round(min(raw_score, 100), 1),
            "estimated_share_pct": round(share, 1),
            "preferred_route": preferred_route,
            "reason_tags": reasons,
            "port": port,
        })

    route_totals = {}
    for item in ports:
        route = item["preferred_route"]
        route_totals[route] = route_totals.get(route, 0) + item["estimated_share_pct"]
    routes = [
        {"route": route, "estimated_share_pct": round(share, 1)}
        for route, share in sorted(route_totals.items(), key=lambda row: row[1], reverse=True)
    ][:6]

    origin_mix = []
    for i, origin in enumerate(profile["origin_regions"][:5]):
        base = max(38 - i * 7, 8)
        origin_mix.append({"origin": origin, "estimated_share_pct": base})
    mix_total = sum(row["estimated_share_pct"] for row in origin_mix) or 1
    for row in origin_mix:
        row["estimated_share_pct"] = round(row["estimated_share_pct"] / mix_total * 100, 1)

    return {
        "hts_code": hts_code,
        "chapter": chapter,
        "category": profile["category"],
        "destination_country": destination_country or "United States",
        "ports": ports,
        "routes": routes,
        "origin_mix": origin_mix,
        "methodology": "Modeled from HTS chapter, commodity category, port specialties, route alignments, throughput, congestion, and demurrage. Not live customs entry volume.",
    }


def _origin_route_fit(port: dict, origin_country: str) -> tuple[float, str]:
    origin = (origin_country or "").lower()
    routes = port.get("primary_routes", [])
    route_text = " ".join(routes).lower()
    if not origin:
        return 0, "No origin country was provided; confirm carrier service before booking."

    for route in routes:
        route_l = route.lower()
        if origin in route_l or route_l in origin:
            return 24, f"Primary services include {route}, matching the selected origin."

    regional_lanes = [
        ("Asia", ["china", "japan", "korea", "taiwan", "vietnam", "thailand", "malaysia", "singapore", "india", "hong kong"]),
        ("Europe", ["germany", "netherlands", "belgium", "spain", "france", "italy", "united kingdom", "uk"]),
        ("South America", ["brazil", "argentina", "chile", "peru", "colombia"]),
        ("Central America", ["mexico", "guatemala", "honduras", "costa rica", "panama"]),
        ("Middle East", ["united arab emirates", "uae", "saudi", "qatar", "oman", "turkey"]),
    ]
    for lane, countries in regional_lanes:
        if any(country in origin for country in countries) and lane.lower() in route_text:
            return 16, f"Primary services include {lane}, a practical regional lane for {origin_country}."

    if "asia" in route_text and any(country in origin for country in ["china", "vietnam", "japan", "korea", "taiwan", "india"]):
        return 14, f"Asia service coverage is a reasonable fit for {origin_country}."

    return 4, f"Carrier service from {origin_country} should be verified for this gateway."


def _product_fit(port: dict, product_description: str) -> tuple[float, str]:
    product = (product_description or "").lower()
    if not product:
        return 0, "General cargo fit; add a product or HTS code for a tighter recommendation."

    best_for = port.get("best_for", [])
    best_for_text = " ".join(best_for).lower()
    product_terms = [term for term in product.replace("/", " ").replace("-", " ").split() if len(term) > 3]
    if any(term in best_for_text for term in product_terms):
        return 18, f"Cargo specialties include {', '.join(best_for[:3])}."

    category_aliases = {
        "electronics": ["electronics", "computer", "semiconductor", "device", "battery"],
        "apparel": ["apparel", "shirt", "textile", "garment", "fashion", "footwear"],
        "automotive": ["auto", "vehicle", "car", "truck", "parts"],
        "food": ["food", "fruit", "meat", "seafood", "beverage", "perishable"],
        "machinery": ["machine", "machinery", "equipment", "industrial"],
        "chemicals": ["chemical", "plastic", "rubber", "pharma"],
    }
    for category, aliases in category_aliases.items():
        if any(alias in product for alias in aliases) and category in best_for_text:
            return 14, f"Cargo specialization aligns with {category} traffic."

    return 2, "No exact cargo specialty match, but the port handles broad containerized cargo."


def _modeled_port_recommendations(body: PortRecommendRequest) -> dict:
    destination_country = body.destination_country or "United States"
    product_note = body.product_description or (f"HTS {body.hts_code}" if body.hts_code else "general cargo")
    chapter = _chapter_from_code(body.hts_code or body.product_description or "")
    profile = _trade_profile(chapter) if chapter else None
    scored = []

    for port in PORTS:
        score = 36.0
        notes = []
        port_country = (port.get("country") or "").lower()
        dest_country = destination_country.lower()

        if port_country == dest_country:
            score += 28
            notes.append(f"Direct gateway in {destination_country}.")
        elif dest_country != "united states" and port_country != "united states":
            score += 10
            notes.append("Practical global gateway or transshipment option.")
        else:
            score -= 10
            notes.append(f"Not located in the destination market of {destination_country}.")

        route_score, route_note = _origin_route_fit(port, body.origin_country)
        product_score, product_fit = _product_fit(port, product_note)
        score += route_score + product_score
        notes.extend([route_note, product_fit])

        if profile:
            if port["code"] in profile["preferred_ports"]:
                score += 16
                notes.append(f"HTS chapter {chapter} aligns with this port's commodity pattern.")
            best_for_text = " ".join(port.get("best_for", [])).lower()
            if any(term.lower() in best_for_text for term in profile["cargo_terms"]):
                score += 10
                notes.append(f"Cargo profile: {profile['category']}.")
            route_text = " ".join(port.get("primary_routes", [])).lower()
            if any(route.lower() in route_text for route in profile["route_bias"]):
                score += 6

        volume = float(port.get("annual_teus_millions") or 0)
        score += min((volume ** 0.5) * 5, 18)

        demurrage_days = float(port.get("avg_demurrage_days") or 0)
        processing_days = float(port.get("avg_processing_days") or 0)
        demurrage_rate = float(port.get("demurrage_rate_usd_per_day") or 0)
        congestion = port.get("congestion_level", "Medium")

        if body.priority == "low_demurrage":
            score += max(0, 18 - demurrage_days * 4)
            notes.append("Scored heavily for low demurrage exposure.")
        elif body.priority == "speed":
            score += max(0, 16 - processing_days * 4)
            notes.append("Scored heavily for processing speed.")
        elif body.priority == "cost":
            score += max(0, 18 - demurrage_rate / 18)
            notes.append("Scored heavily for lower daily demurrage cost.")
        else:
            score += max(0, 12 - demurrage_days * 2)

        score -= {"Low": 0, "Medium": 5, "High": 12}.get(congestion, 5)
        score = max(1, min(99, round(score)))

        considerations = port.get("considerations") or []
        if congestion == "High":
            risk_note = "High congestion can increase dwell time, storage charges, and appointment pressure."
        elif considerations:
            risk_note = considerations[0]
        else:
            risk_note = "Risk profile is comparatively stable; still confirm sailing schedule and free time."

        scored.append({
            "code": port["code"],
            "score": score,
            "reason": " ".join(notes[:3]),
            "demurrage_advantage": f"{demurrage_days:g} day average demurrage at ${int(demurrage_rate)}/day.",
            "route_fit": route_note,
            "inland_fit": (port.get("strengths") or [f"{port['region']} gateway for {destination_country}."])[0],
            "risk_note": risk_note,
        })

    top_picks = sorted(scored, key=lambda row: row["score"], reverse=True)[:3]
    for rank, pick in enumerate(top_picks, start=1):
        pick["rank"] = rank

    best = next((p for p in PORTS if p["code"] == top_picks[0]["code"]), None) if top_picks else None
    summary = (
        f"{best['name']} is the strongest modeled fit for {body.origin_country} to {destination_country} "
        f"based on route alignment, cargo fit, congestion, demurrage, and throughput. "
        f"Use the port profile to validate inland access and risk before booking."
        if best else "No matching ports were available for this recommendation."
    )
    return {"top_picks": top_picks, "summary": summary}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/ports")
async def list_ports():
    return {"ports": PORTS}


@router.get("/trade/heatmap")
async def trade_heatmap(
    hts_code: str = Query(..., min_length=2),
    destination_country: str = Query("United States"),
):
    code = hts_code.strip()
    if not any(ch.isdigit() for ch in code):
        raise HTTPException(400, "Enter an HTS code with at least two digits")
    ck = cache.cache_key("trade_heatmap", code, destination_country or "United States")
    cached = cache.get("trade_heatmap", ck, ttl=3600)
    if cached is not None:
        return cached
    result = _modeled_trade_heatmap(code, destination_country or "United States")
    cache.put("trade_heatmap", ck, result)
    return result


@router.post("/shipping/estimate")
async def shipping_estimate(body: ShippingEstimateRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(503, "Shipping estimates require OPENAI_API_KEY")

    # Check cache first
    destination_zip = (body.destination_zip or "").strip()
    ck = cache.cache_key("ship", body.origin_country, body.destination_country or "",
                         body.destination_port or "",
                         destination_zip,
                         body.weight_kg, body.volume_cbm, body.product_description or "",
                         body.cargo_value_usd or 0)
    cached = cache.get("shipping_estimate", ck, ttl=1800)
    if cached is not None:
        print(f"[shipping] Cache hit for estimate")
        return cached

    client = OpenAI(api_key=OPENAI_API_KEY)

    destination_country = body.destination_country or "United States"
    zip_suffix = f" (ZIP {destination_zip})" if destination_zip else ""
    dest_note = (
        f"to {body.destination_port}, {destination_country}{zip_suffix}"
        if body.destination_port else f"to {destination_country}{zip_suffix}"
    )
    product_note = body.product_description or (f"HTS {body.hts_code}" if body.hts_code else "general cargo")
    value_note = f"${body.cargo_value_usd:,.0f}" if body.cargo_value_usd else "undeclared"

    inland_instruction = ""
    if destination_zip and destination_country.lower() == "united states":
        inland_instruction = (
            f"\nThe cargo must be delivered to US ZIP code {destination_zip}. "
            f"Include realistic US domestic inland transport (port-to-door) in each option's "
            f"estimated_cost_usd, and note the inland-leg cost and likely mode (LTL, FTL, parcel, drayage + rail) in 'notes'."
        )

    prompt = (
        f"You are a freight shipping expert with current market knowledge (2025).\n\n"
        f"Estimate shipping costs for:\n"
        f"- Route: {body.origin_country} → {dest_note}\n"
        f"- Weight: {body.weight_kg} kg\n"
        f"- Volume: {body.volume_cbm} CBM\n"
        f"- Product: {product_note}\n"
        f"- Cargo value: {value_note}"
        f"{inland_instruction}\n\n"
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
            "destination_country": destination_country,
            "destination_zip": destination_zip,
            "weight_kg": body.weight_kg,
            "volume_cbm": body.volume_cbm,
        }}
        cache.put("shipping_estimate", ck, result)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to generate estimates: {e}")


@router.post("/ports/recommend")
async def recommend_ports(body: PortRecommendRequest):
    # Check cache first
    ck = cache.cache_key("recommend", body.origin_country, body.destination_country or "",
                         body.product_description or "", body.hts_code or "",
                         body.priority or "balanced")
    cached = cache.get("port_recommend", ck, ttl=1800)
    if cached is not None:
        print(f"[ports] Cache hit for recommendation")
        return cached

    fallback = _modeled_port_recommendations(body)
    if not OPENAI_API_KEY:
        cache.put("port_recommend", ck, fallback)
        return fallback

    client = OpenAI(api_key=OPENAI_API_KEY)

    ports_summary = "\n".join(
        f"- [{p['code']}] {p['name']} | Country: {p['country']} | Region: {p['region']} | Avg demurrage: {p['avg_demurrage_days']} days "
        f"| Congestion: {p['congestion_level']} | Routes: {', '.join(p['primary_routes'][:3])}"
        for p in PORTS
    )

    product_note = body.product_description or (f"HTS {body.hts_code}" if body.hts_code else "general cargo")

    prompt = (
        f"You are a port logistics expert.\n\n"
        f"Recommend the best destination gateway ports for:\n"
        f"- Origin country: {body.origin_country}\n"
        f"- Destination country/market: {body.destination_country or 'United States'}\n"
        f"- Product: {product_note}\n"
        f"- Priority: {body.priority}\n\n"
        f"Available ports:\n{ports_summary}\n\n"
        f"Return ONLY this JSON (no other text):\n"
        f'{{\n'
        f'  "top_picks": [\n'
        f'    {{"code": "USSAV", "rank": 1, "score": 92, "reason": "why this port fits best", '
        f'"demurrage_advantage": "1.9 days vs 3.5 avg", '
        f'"route_fit": "how the selected origin country maps to this port lane", '
        f'"inland_fit": "why this gateway fits the destination market", '
        f'"risk_note": "main operational risk to validate before booking"}}\n'
        f'  ],\n'
        f'  "summary": "2-sentence overall recommendation"\n'
        f'}}\n\n'
        f"Return 3 top picks ranked 1-3. Prefer ports in the destination country when available; "
        f"otherwise recommend the closest practical global gateways or transshipment hubs."
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
        fallback_by_code = {pick["code"]: pick for pick in fallback.get("top_picks", [])}
        for idx, pick in enumerate(result.get("top_picks", [])):
            modeled = fallback_by_code.get(pick.get("code")) or (
                fallback["top_picks"][idx] if idx < len(fallback.get("top_picks", [])) else {}
            )
            for key in ("score", "reason", "demurrage_advantage", "route_fit", "inland_fit", "risk_note"):
                if not pick.get(key) and modeled.get(key):
                    pick[key] = modeled[key]
            pick.setdefault("rank", idx + 1)
        if not result.get("summary"):
            result["summary"] = fallback["summary"]
        cache.put("port_recommend", ck, result)
        return result
    except Exception:
        cache.put("port_recommend", ck, fallback)
        return fallback
