"""
Brand configurations and store data for content generation.
References STORE_REGISTRY but adds content-specific context.
"""

BRAND_CONFIG = {
    "bakudan": {
        "brand_name": "Bakudan Ramen",
        "brand_short": "Bakudan",
        "cuisine": "Authentic Japanese Ramen",
        "website_domain": "bakudanramen.com",
        "project_id": "BakudanWebsite_Sub",
        "city": "San Antonio, TX",
        "signature_dishes": [
            "Tonkotsu Ramen (12-hour pork bone broth)",
            "Spicy Miso Ramen",
            "Chicken Paitan Ramen",
            "Chashu Pork",
            "Gyoza",
            "Takoyaki",
        ],
        "brand_tone": "Bold, authentic, passionate about craft. Japanese soul with Texas heart.",
        "stores": {
            "B1": {
                "name": "Bakudan Ramen - The Rim",
                "address": "17619 La Cantera Pkwy UNIT 208, San Antonio, TX",
                "phone": "(210) 257-8080",
                "area_context": "The Rim/La Cantera shopping district — popular with tourists and families",
            },
            "B2": {
                "name": "Bakudan Ramen - Stone Oak",
                "address": "22506 U.S. Hwy 281 N Ste 106, San Antonio, TX",
                "phone": "(210) 437-0632",
                "area_context": "Stone Oak — upscale north-side neighborhood, professionals and families",
            },
            "B3": {
                "name": "Bakudan Ramen - Bandera",
                "address": "11309 Bandera Rd Ste 111, San Antonio, TX",
                "phone": "(210) 277-7740",
                "area_context": "Bandera/Helotes corridor — fast-growing suburban area",
            },
        },
        "local_themes": [
            "San Antonio Riverwalk dining",
            "The Rim shopping and food scene",
            "Stone Oak restaurant week",
            "Texas Hill Country day trips",
            "Fiesta San Antonio events",
            "San Antonio Spurs game day dining",
        ],
        "tourist_themes": [
            "Best ramen in San Antonio",
            "Where to eat near the Alamo",
            "San Antonio food guide for visitors",
            "Authentic Japanese food in Texas",
            "Riverwalk restaurants worth the walk",
            "Hidden gems near La Cantera",
        ],
        "menu_themes": [
            "How tonkotsu broth is made (12-hour process)",
            "Guide to ramen toppings and customization",
            "Japanese bar snacks: gyoza, takoyaki, edamame",
            "What makes authentic chashu pork",
            "Happy hour specials and sake pairings",
            "Seasonal specials and limited-time menu items",
        ],
    },
    "raw": {
        "brand_name": "Raw Sushi Bar",
        "brand_short": "Raw",
        "cuisine": "Premium Japanese Sushi & Sashimi",
        "website_domain": "rawsushibar.com",
        "project_id": "RawWebsite",
        "city": "Stockton, CA",
        "signature_dishes": [
            "Chef's Omakase",
            "Dragon Roll",
            "Fresh Salmon Sashimi",
            "Yellowtail Jalapeño",
            "Baked Lobster Roll",
            "Tuna Tataki",
        ],
        "brand_tone": "Refined, fresh, artistic. Emphasize freshness, craft, and the art of sushi.",
        "stores": {
            "RAW": {
                "name": "Raw Sushi Bar - Stockton",
                "address": "10742 Trinity Parkway, Suite D, Stockton, CA",
                "phone": "(209) 954-9729",
                "area_context": "Stockton/Central Valley — serving the community for 20+ years",
                "hours": "Mon-Thu 4:30-8:30PM, Fri 11:30AM-9PM, Sat 12-9PM, Sun 12-8PM",
            },
        },
        "local_themes": [
            "Stockton's best sushi restaurant",
            "Central Valley dining guide",
            "Date night ideas in Stockton",
            "Catering for events and parties",
            "Supporting local Stockton community",
            "Modesto and Lodi residents: worth the drive",
        ],
        "tourist_themes": [
            "Best sushi near Sacramento",
            "Central Valley hidden food gems",
            "California sushi culture guide",
            "Delta region dining destinations",
            "Highway 99 food stops",
            "Japanese food in Stockton",
        ],
        "menu_themes": [
            "The art of sashimi: choosing the freshest fish",
            "Nigiri vs sashimi vs maki: a guide",
            "Sushi etiquette: how to eat like a pro",
            "Sustainable seafood at Raw Sushi Bar",
            "Omakase experience: trust the chef",
            "Sake pairing guide for sushi",
        ],
    },
}


def get_brand_config(brand: str) -> dict:
    """Get full brand configuration."""
    return BRAND_CONFIG.get(brand, {})


def get_store_context(brand: str) -> str:
    """Build a store context string for LLM prompts."""
    cfg = get_brand_config(brand)
    if not cfg:
        return ""

    lines = [f"Brand: {cfg['brand_name']}", f"Cuisine: {cfg['cuisine']}", f"City: {cfg['city']}", ""]
    lines.append("Locations:")
    for sid, store in cfg.get("stores", {}).items():
        lines.append(f"  {store['name']}")
        lines.append(f"    Address: {store['address']}")
        lines.append(f"    Phone: {store['phone']}")
        if store.get("hours"):
            lines.append(f"    Hours: {store['hours']}")
        if store.get("area_context"):
            lines.append(f"    Area: {store['area_context']}")
    lines.append("")
    lines.append(f"Signature dishes: {', '.join(cfg.get('signature_dishes', []))}")
    lines.append(f"Brand tone: {cfg.get('brand_tone', '')}")
    return "\n".join(lines)
