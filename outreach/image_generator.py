"""Generate images for demo sites via Nano Banana (Google Gemini).

Falls back to curated Unsplash stock-photo URLs when the API key is not
configured or a generation call fails.
"""

import io
import logging

from config import GOOGLE_API_KEY, IMAGE_MODEL

logger = logging.getLogger(__name__)

# ─── Unsplash fallback URLs per trade ────────────────────────────────
# Free, no API key needed.  Each URL is a direct-link Unsplash photo
# resized via query parameters.  We keep 1 hero, 1 about, and 4 gallery
# images per trade.

_UNSPLASH = "https://images.unsplash.com"

TRADE_UNSPLASH = {
    "General Contractor": {
        "hero": f"{_UNSPLASH}/photo-1504307651254-35680f356dfd?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1581094794329-c8112a89af12?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1503387762-592deb58ef4e?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1541123603104-512919d6a96c?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1585128903994-9788298932a4?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1622015663319-e97e697503ee?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Roofer": {
        "hero": f"{_UNSPLASH}/photo-1632759145354-d3ed0dae1a15?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1607400201889-565b1ee75f8e?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1558618666-fcd25c85f82e?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1600585154340-be6161a56a0c?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1632759145351-76802dc29cba?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1598228723793-52759bba239c?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Electrician": {
        "hero": f"{_UNSPLASH}/photo-1621905251189-08b45d6a269e?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1558618666-fcd25c85f82e?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1558618666-fcd25c85f82e?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1621905252507-b35492cc74b4?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1555664424-778a1e5e1b48?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1544724569-5f546fd6f2b5?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Plumber": {
        "hero": f"{_UNSPLASH}/photo-1585704032915-c3400ca199e7?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1607472586893-edb57bdc0e39?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1585704032915-c3400ca199e7?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1504328345606-18bbc8c9d7d1?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1558618666-fcd25c85f82e?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1581092921461-eab62e97a780?w=600&h=450&fit=crop&q=80",
        ],
    },
    "HVAC": {
        "hero": f"{_UNSPLASH}/photo-1631545806609-16d0a8e0c131?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1581094794329-c8112a89af12?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1631545806609-16d0a8e0c131?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1558618666-fcd25c85f82e?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1504307651254-35680f356dfd?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1585128903994-9788298932a4?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Landscaper": {
        "hero": f"{_UNSPLASH}/photo-1558904541-efa843a96f01?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1592417817098-8fd3d9eb14a5?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1558904541-efa843a96f01?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1585320806297-9794b3e4eeae?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1600607687939-ce8a6c25118c?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1416879595882-3373a0480b5b?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Solar Installer": {
        "hero": f"{_UNSPLASH}/photo-1509391366360-2e959784a276?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1558449028-b53a39d100fc?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1509391366360-2e959784a276?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1508514177221-188b1cf16e9d?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1613665813446-82a78c468a1d?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1559302504-64aae6ca6b6d?w=600&h=450&fit=crop&q=80",
        ],
    },
    "Painter": {
        "hero": f"{_UNSPLASH}/photo-1562259929-b4e1fd3aef09?w=1400&h=700&fit=crop&q=80",
        "about": f"{_UNSPLASH}/photo-1581094794329-c8112a89af12?w=800&h=600&fit=crop&q=80",
        "gallery": [
            f"{_UNSPLASH}/photo-1562259929-b4e1fd3aef09?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1589939705384-5185137a7f0f?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1513694203232-719a280e022f?w=600&h=450&fit=crop&q=80",
            f"{_UNSPLASH}/photo-1560185893-a55cbc8c57e8?w=600&h=450&fit=crop&q=80",
        ],
    },
}

# Default fallback for trades not listed above
_DEFAULT_UNSPLASH = {
    "hero": f"{_UNSPLASH}/photo-1504307651254-35680f356dfd?w=1400&h=700&fit=crop&q=80",
    "about": f"{_UNSPLASH}/photo-1581094794329-c8112a89af12?w=800&h=600&fit=crop&q=80",
    "gallery": [
        f"{_UNSPLASH}/photo-1503387762-592deb58ef4e?w=600&h=450&fit=crop&q=80",
        f"{_UNSPLASH}/photo-1541123603104-512919d6a96c?w=600&h=450&fit=crop&q=80",
        f"{_UNSPLASH}/photo-1585128903994-9788298932a4?w=600&h=450&fit=crop&q=80",
        f"{_UNSPLASH}/photo-1622015663319-e97e697503ee?w=600&h=450&fit=crop&q=80",
    ],
}


# ─── Trade-specific AI image prompts ─────────────────────────────────

TRADE_IMAGE_PROMPTS = {
    "General Contractor": {
        "hero": "Professional home renovation in progress, modern open-concept kitchen remodel with exposed beams, warm natural lighting, high-end residential construction, editorial photography style",
        "about": "Friendly professional construction team of 4 standing together at a beautiful finished home project, hard hats, smiling, golden hour, commercial photography",
        "gallery": [
            "Stunning modern kitchen renovation with white quartz countertops, custom cabinetry, pendant lights, professional real estate photography",
            "Beautiful bathroom remodel with walk-in shower, marble tile, modern vanity, luxury residential design",
            "Custom home addition with large windows and hardwood floors, open plan living room, natural light",
            "Finished basement renovation with entertainment area, recessed lighting, engineered hardwood, modern design",
        ],
    },
    "Roofer": {
        "hero": "Aerial drone photo of a beautiful residential home with brand new architectural shingle roof, clean gutters, sunny day, suburban neighborhood, real estate photography",
        "about": "Professional roofing crew of 4 standing on the ground next to a completed roofing project, wearing safety gear, friendly team photo, commercial photography",
        "gallery": [
            "New charcoal architectural shingle roof installation on a two-story colonial home, perfect lines, sunny day",
            "Modern standing seam metal roof on a contemporary farmhouse, dramatic sky, architectural photography",
            "Close-up detail of premium slate roof tiles with copper flashing, craftsmanship detail shot",
            "Before and after split image showing old worn roof replaced with beautiful new roof, transformation photo",
        ],
    },
    "Electrician": {
        "hero": "Modern smart home electrical panel with organized wiring, LED lighting throughout a luxury home hallway, professional electrical work, clean and precise",
        "about": "Licensed electrician in clean uniform working on a modern electrical panel, professional and focused, well-lit workshop environment",
        "gallery": [
            "Beautiful recessed LED lighting installation in a modern kitchen, warm ambient glow, interior design photography",
            "Professional whole-house generator installation next to a suburban home, clean setup",
            "Modern smart home lighting control panel on a wall, touchscreen interface, contemporary interior",
            "Outdoor landscape lighting illuminating a beautiful garden path at dusk, architectural lighting design",
        ],
    },
    "Plumber": {
        "hero": "Luxurious modern bathroom with freestanding bathtub, rain shower, polished fixtures, professional plumbing installation, interior design photography",
        "about": "Friendly professional plumber in clean uniform with tools, standing in a modern kitchen, smiling, trustworthy appearance, commercial photography",
        "gallery": [
            "Modern kitchen sink with touchless faucet and garbage disposal, quartz countertop, professional installation",
            "Tankless water heater professionally mounted on a utility room wall, clean piping, organized setup",
            "Walk-in shower with rain head and body jets, glass enclosure, tile work, luxury bathroom",
            "Outdoor hose bib and irrigation system connection, clean copper piping, professional workmanship",
        ],
    },
    "HVAC": {
        "hero": "Modern home HVAC system with sleek thermostat on wall, comfortable family living room in background, warm cozy atmosphere, lifestyle photography",
        "about": "HVAC technician in professional uniform inspecting a modern air conditioning system, commercial setting, professional photography",
        "gallery": [
            "Sleek modern ductless mini-split system mounted on a living room wall, clean installation, contemporary interior",
            "High-efficiency furnace installation in a clean utility room, organized ductwork, professional setup",
            "Smart thermostat display showing energy savings, modern home interior background",
            "Commercial rooftop HVAC unit on a modern building, blue sky, professional equipment photography",
        ],
    },
    "Landscaper": {
        "hero": "Stunning landscape design with stone patio, outdoor kitchen, lush garden beds, ornamental trees, golden hour lighting, aerial perspective, landscape architecture photography",
        "about": "Professional landscaping team of 3 standing in a beautifully designed garden, wearing company uniforms, friendly, outdoor commercial photography",
        "gallery": [
            "Custom flagstone patio with built-in fire pit, outdoor seating area, lush perennial border, evening lighting",
            "Professional sod installation on a residential lawn, perfectly green and level, irrigation system visible",
            "Elegant front yard landscape with stone walkway, ornamental grasses, flowering shrubs, curb appeal",
            "Backyard water feature with natural stone waterfall, pond, surrounded by ferns and hostas, tranquil setting",
        ],
    },
    "Solar Installer": {
        "hero": "Sleek solar panel array installed on a modern residential roof, clear blue sky, suburban home, clean energy, drone photography perspective",
        "about": "Solar installation team in safety gear on a rooftop with solar panels, professional team photo, sunny day, commercial photography",
        "gallery": [
            "Residential solar panel system with battery storage unit in garage, clean installation, modern home",
            "Close-up of premium monocrystalline solar panels catching sunlight, product detail photography",
            "Ground-mounted solar array in a residential backyard, tracking system, green lawn",
            "Solar panel installation in progress on a new construction home, crew working, professional",
        ],
    },
    "Painter": {
        "hero": "Freshly painted modern home exterior in elegant gray with white trim, beautiful curb appeal, sunny day, real estate photography style",
        "about": "Professional painter in clean white overalls holding a roller, standing next to freshly painted wall in designer color, friendly, commercial photo",
        "gallery": [
            "Stunning accent wall painted in deep navy blue in a modern living room, crisp edges, designer interior",
            "Freshly painted kitchen cabinets in sage green, brass hardware, professional cabinet painting finish",
            "Beautiful exterior house painting job showing crisp trim work, multiple colors, Victorian detail",
            "Deck staining before and after, rich cedar tone, wood grain visible, outdoor improvement",
        ],
    },
    "Lawn Care": {
        "hero": "Perfectly manicured residential lawn with crisp edging, lush green grass, well-maintained flower beds, suburban home, aerial view, real estate photography",
        "about": "Professional lawn care technician with commercial mower on a beautiful lawn, company uniform, sunny day, commercial photography",
        "gallery": [
            "Freshly mowed lawn with diagonal striping pattern, pristine edging along sidewalk and beds",
            "Lawn aeration in progress with visible soil plugs, healthy thick grass, professional equipment",
            "Fall leaf cleanup showing half-cleaned lawn, blower in use, satisfying before/after contrast",
            "Lush overseeded lawn in early spring, thick green grass filling in, irrigation running",
        ],
    },
    "Tree Service": {
        "hero": "Professional arborist performing tree trimming high in a large oak tree, safety harness, chainsaw, dramatic angle looking up, blue sky background",
        "about": "Tree service crew with bucket truck and chipper in front of a large tree, safety gear, professional team photo, commercial photography",
        "gallery": [
            "Large dead tree being carefully removed in sections near a house, crane assist, professional operation",
            "Stump grinding in progress showing the machine creating fine mulch, satisfying removal process",
            "Beautiful ornamental tree after expert pruning, perfect shape, healthy canopy, residential yard",
            "Emergency storm damage cleanup, fallen tree removed from property, crew working efficiently",
        ],
    },
    "Pest Control": {
        "hero": "Clean modern home exterior with a protective barrier, pest-free family enjoying their backyard, warm inviting atmosphere, lifestyle photography",
        "about": "Professional pest control technician in uniform with modern equipment, inspecting a home exterior, friendly, commercial photography",
        "gallery": [
            "Pest control barrier treatment being applied around home foundation, professional spray equipment",
            "Termite inspection in progress with technician using moisture meter on wood, detailed work",
            "Modern bait station professionally installed near home exterior, discreet and effective",
            "Happy family relaxing on pest-free patio in their backyard, enjoying summer evening",
        ],
    },
    "Cleaning Service": {
        "hero": "Sparkling clean modern living room with gleaming hardwood floors, spotless surfaces, bright natural light, organized and pristine, real estate photography",
        "about": "Professional cleaning team in matching uniforms with modern cleaning equipment, friendly, standing in a beautiful clean home, commercial photography",
        "gallery": [
            "Spotless modern kitchen with gleaming stainless steel appliances, clean countertops, organized",
            "Deep cleaned bathroom with sparkling tile, streak-free mirrors, fresh towels, hotel quality",
            "Freshly cleaned hardwood floors reflecting natural light, dust-free baseboards, perfection",
            "Post-construction cleanup showing pristine finished space, all debris removed, move-in ready",
        ],
    },
    "Handyman": {
        "hero": "Professional handyman completing a custom shelving installation in a modern home office, organized tools, quality craftsmanship, warm interior lighting",
        "about": "Friendly handyman with tool belt standing in a doorway of a beautiful home, smiling, trustworthy, professional appearance, commercial photography",
        "gallery": [
            "Custom floating shelves professionally mounted on a living room wall, level and secure, modern decor",
            "Door replacement installation, new modern door perfectly hung, clean trim work, quality finish",
            "Drywall repair and painting, seamless patch invisible after finish, professional quality",
            "Ceiling fan installation in a bedroom, modern fixture, clean electrical work, balanced and quiet",
        ],
    },
    "Fencing Contractor": {
        "hero": "Beautiful cedar privacy fence with decorative lattice top bordering a lush backyard, golden hour lighting, residential property, landscape photography",
        "about": "Professional fencing crew installing a new fence, measuring and setting posts, teamwork, commercial photography",
        "gallery": [
            "Modern horizontal slat cedar fence with black metal posts, contemporary design, backyard privacy",
            "White vinyl picket fence along a beautiful front yard, classic American style, curb appeal",
            "Custom wrought iron gate with decorative scrollwork, elegant entrance, upscale residential",
            "Chain link fence with privacy slats around a commercial property, clean installation, secure",
        ],
    },
    "Pressure Washing": {
        "hero": "Dramatic before-and-after split of a concrete driveway being pressure washed, one side gleaming clean, the other dirty, satisfying transformation",
        "about": "Professional pressure washing technician in safety gear operating commercial equipment on a driveway, action shot, commercial photography",
        "gallery": [
            "House siding being pressure washed with visible clean streak, dramatic contrast, before and after",
            "Brick patio restored to original color by pressure washing, furniture moved aside, transformation",
            "Wooden deck being soft washed, revealing natural wood grain underneath years of grime",
            "Commercial parking lot being pressure washed with surface cleaner, systematic clean lines",
        ],
    },
}

# Default prompts for trades not listed above
_DEFAULT_PROMPTS = {
    "hero": "Professional contractor team working on a residential project, high quality workmanship, sunny day, commercial photography style",
    "about": "Friendly professional service team standing together, uniforms, smiling, commercial photography",
    "gallery": [
        "Beautiful completed home improvement project, modern design, professional quality",
        "Professional crew working on a residential project, teamwork, quality craftsmanship",
        "Finished project detail shot showing quality materials and workmanship, close-up",
        "Happy homeowner inspecting completed work with contractor, satisfaction, handshake",
    ],
}


# ─── Public API ──────────────────────────────────────────────────────

def is_configured() -> bool:
    """Return True if the Nano Banana API key is set."""
    return bool(GOOGLE_API_KEY)


def generate_image(prompt: str, aspect_ratio: str = "16:9") -> bytes | None:
    """Generate a single image from a text prompt via Nano Banana.

    Returns raw PNG bytes on success, or ``None`` on failure.
    """
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set — skipping image generation")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            ),
        )

        # Extract the first image part
        for part in response.parts:
            if part.inline_data is not None:
                raw = part.inline_data.data
                mime = getattr(part.inline_data, "mime_type", "")
                # Convert to JPEG for smaller file size (unless already JPEG)
                if "jpeg" in mime or "jpg" in mime:
                    return raw
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(io.BytesIO(raw))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    return buf.getvalue()
                except ImportError:
                    # Pillow not installed — return raw bytes as-is
                    return raw

        logger.warning("No image returned in Nano Banana response")
        return None

    except Exception as e:
        logger.error("Nano Banana image generation failed: %s", e)
        return None


def generate_hero_image(trade: str, business_name: str, location: str = "") -> bytes | None:
    """Generate a hero background image for a trade/business."""
    prompts = TRADE_IMAGE_PROMPTS.get(trade, _DEFAULT_PROMPTS)
    prompt = prompts["hero"]
    if business_name:
        prompt += f", for {business_name}"
    if location:
        prompt += f" in {location}"
    return generate_image(prompt, aspect_ratio="16:9")


def generate_about_image(trade: str, business_name: str = "") -> bytes | None:
    """Generate an about-section team/business image."""
    prompts = TRADE_IMAGE_PROMPTS.get(trade, _DEFAULT_PROMPTS)
    prompt = prompts["about"]
    if business_name:
        prompt += f", {business_name} team"
    return generate_image(prompt, aspect_ratio="4:3")


def generate_gallery_images(trade: str, count: int = 4) -> list[bytes | None]:
    """Generate portfolio/gallery images for a trade.

    Returns a list of up to *count* image byte objects.  Items may be
    ``None`` if individual generations fail.
    """
    prompts = TRADE_IMAGE_PROMPTS.get(trade, _DEFAULT_PROMPTS)
    gallery_prompts = prompts.get("gallery", _DEFAULT_PROMPTS["gallery"])

    images = []
    for i, prompt in enumerate(gallery_prompts[:count]):
        logger.info("Generating gallery image %d/%d for %s", i + 1, count, trade)
        img = generate_image(prompt, aspect_ratio="4:3")
        images.append(img)

    return images


def generate_logo(trade: str, business_name: str) -> bytes | None:
    """Generate a simple icon-style logo mark for a business.

    Returns PNG bytes (with transparency) or None on failure.
    """
    trade_lower = trade.lower()
    prompt = (
        f"Design a minimal, modern logo icon for '{business_name}', a professional "
        f"{trade_lower} company. The logo should be a simple, clean icon mark — NOT text. "
        f"Use a single recognizable symbol related to {trade_lower} work. "
        f"Flat design, solid colors, no gradients, no shadows, no background. "
        f"Professional and corporate feel. White icon on transparent background. "
        f"Think of app icons or favicon-style marks. Square aspect ratio."
    )
    img_bytes = generate_image(prompt, aspect_ratio="1:1")
    if img_bytes:
        # Keep as PNG for transparency support
        try:
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(img_bytes))
            # Resize to a reasonable logo size (200x200)
            img = img.resize((200, 200), PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except (ImportError, Exception):
            return img_bytes
    return None


def get_unsplash_urls(trade: str) -> dict:
    """Return Unsplash fallback URLs for a trade.

    Returns dict with 'hero', 'about', and 'gallery' keys.
    """
    return TRADE_UNSPLASH.get(trade, _DEFAULT_UNSPLASH)
