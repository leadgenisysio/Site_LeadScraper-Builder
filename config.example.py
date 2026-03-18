"""Configuration for the lead scraper."""

# Target states with their abbreviations and full names
STATES = {
    "NH": "New Hampshire",
    "VT": "Vermont",
    "CT": "Connecticut",
    "MA": "Massachusetts",
    "FL": "Florida",
    "TX": "Texas",
}

# Trade categories to search for
TRADES = {
    "Construction": [
        "General Contractor",
        "Roofer",
        "Electrician",
        "Plumber",
        "HVAC",
        "Mason",
        "Carpenter",
        "Painter",
        "Siding Contractor",
        "Flooring Contractor",
        "Drywall Contractor",
        "Concrete Contractor",
        "Fencing Contractor",
        "Deck Builder",
    ],
    "Home Services": [
        "Landscaper",
        "Lawn Care",
        "Tree Service",
        "Pest Control",
        "Cleaning Service",
        "Handyman",
        "Moving Company",
        "Pressure Washing",
        "Junk Removal",
        "Garage Door Repair",
        "Locksmith",
        "Appliance Repair",
        "Chimney Sweep",
        "Gutter Cleaning",
        "Pool Service",
        "Septic Service",
        "Paving",
    ],
    "Solar": [
        "Solar Installer",
        "Solar Panel Company",
        "Solar Energy Contractor",
        "Solar Roofing",
    ],
}

# Flat list of all trades
ALL_TRADES = []
for category in TRADES.values():
    ALL_TRADES.extend(category)

# Domains to exclude from search results (major platforms, not contractor sites)
EXCLUDED_DOMAINS = [
    # Major directories / aggregators
    "yelp.com",
    "angi.com",
    "angieslist.com",
    "homeadvisor.com",
    "thumbtack.com",
    "bbb.org",
    "houzz.com",
    "porch.com",
    "buildzoom.com",
    "bark.com",
    "expertise.com",
    "chamberofcommerce.com",
    "homeguide.com",
    "homestargroup.com",
    # Contractor listing / lead-gen sites
    "plumbersup.com",
    "bestplumbersclub.com",
    "meetaplumber.com",
    "aplumbers.com",
    "plumbersnow.com",
    "prohandyplumber.com",
    "networx.com",
    "fixr.com",
    "improvenet.com",
    "costimates.com",
    "craftjack.com",
    "contractorquotes.us",
    "find-a-contractor.com",
    # National chains (not local contractors)
    "rotorooter.com",
    # Social media
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "nextdoor.com",
    # Yellow/white pages
    "yellowpages.com",
    "superpages.com",
    "whitepages.com",
    "manta.com",
    # Map / search engines
    "google.com",
    "bing.com",
    "yahoo.com",
    "mapquest.com",
    # Other noise
    "amazon.com",
    "craigslist.org",
    "reddit.com",
    "wikipedia.org",
    "dnb.com",
    "indeed.com",
    "glassdoor.com",
    "gov",
]

# Emails to filter out (generic platform/noreply addresses)
EXCLUDED_EMAIL_PATTERNS = [
    # System / no-reply
    "noreply@",
    "no-reply@",
    "donotreply@",
    "mailer-daemon@",
    "postmaster@",
    "abuse@",
    "webmaster@",
    "hostmaster@",
    # Website builder defaults
    "admin@wordpress",
    "admin@wix",
    "admin@squarespace",
    "sitemanager@wpmanager",
    # Placeholder / fake
    "@example.com",
    "@example.org",
    "@mysite.com",
    "@domain.com",
    "@yourdomain.com",
    "your@email",
    "test@test",
    "email@email",
    "info@info",
    # Tech / platform (not real businesses)
    "@sentry.io",
    "@sentry-next.",
    "@ingest.us",
    "@google.com",
    "@facebook.com",
    "@twitter.com",
    "@w3.org",
    "@schema.org",
    "@cloudflare.com",
    "@gravatar.com",
    "@googleapis.com",
    # Media / aggregator sites (not contractors)
    "@energysage.com",
    "@ecowatch.com",
    "@todayshomeowner",
    "@globe.com",
    "@jacksonvillejive",
]

# Non-US country TLDs to exclude (we only target US businesses)
EXCLUDED_COUNTRY_TLDS = [
    ".co.uk", ".uk", ".ca", ".au", ".nz", ".eu",
    ".de", ".fr", ".in", ".jp", ".cn", ".ru",
    ".br", ".mx", ".za", ".ie", ".nl", ".se",
    ".no", ".dk", ".fi", ".it", ".es", ".pt",
    ".pl", ".cz", ".at", ".ch", ".be", ".sg",
    ".hk", ".kr", ".tw", ".ph", ".my", ".id",
]

# Scraper settings
SEARCH_DELAY_SECONDS = 3  # Delay between Google searches
REQUEST_TIMEOUT = 10  # Timeout for fetching contractor websites
DEFAULT_RESULTS_PER_QUERY = 10  # Number of Google results per search query
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Database
DATABASE_PATH = "leads.db"

# Lead statuses
LEAD_STATUSES = ["new", "contacted", "not_interested", "closed"]

# ─── Outreach Settings ───────────────────────────────────────────────

# Netlify deployment (get token at https://app.netlify.com/user/applications#personal-access-tokens)
NETLIFY_API_TOKEN = ""  # ← paste your Netlify personal access token here
NETLIFY_API_BASE = "https://api.netlify.com/api/v1"

# ─── Cloudflare Pages (FREE alternative to Netlify) ────────────────
# Get your API token at https://dash.cloudflare.com/profile/api-tokens
#   → Create Token → "Edit Cloudflare Workers" template (includes Pages)
# Get your Account ID from https://dash.cloudflare.com → any domain → Overview sidebar
CLOUDFLARE_API_TOKEN = ""    # ← paste your Cloudflare API token here
CLOUDFLARE_ACCOUNT_ID = ""   # ← paste your Account ID here

# Which hosting platform to use: "cloudflare" or "netlify"
# Set to "cloudflare" once you add your Cloudflare credentials above
HOSTING_PLATFORM = "netlify"

# Gmail SMTP (enable 2FA, then create App Password at https://myaccount.google.com/apppasswords)
GMAIL_ADDRESS = ""  # ← your Gmail address
# ⬇⬇⬇ PASTE YOUR 16-CHARACTER GMAIL APP PASSWORD BELOW (not your regular password!) ⬇⬇⬇
GMAIL_APP_PASSWORD = ""  # ← your Gmail App Password (enable 2FA first)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Rate limiting
OUTREACH_DAILY_LIMIT = 15
OUTREACH_SEND_DELAY = 30  # seconds between batch emails

# Test mode — when True, ALL outreach emails go to GMAIL_ADDRESS instead of the lead
OUTREACH_TEST_MODE = True

# Your branding (shown in demo sites and email signatures)
SENDER_NAME = ""       # ← your name
SENDER_COMPANY = ""    # ← your company name
SENDER_PHONE = ""      # ← your phone number
SENDER_EMAIL = ""      # ← reply-to email (can differ from GMAIL_ADDRESS)
SENDER_WEBSITE = ""    # ← your website URL (shown in email signature)
SENDER_CALENDAR = ""   # ← booking link for email CTA (GHL, Calendly, etc.)

# ─── A/B Testing: Subject Line Variants ────────────────────────────
# Each variant has an id, a subject template, and an optional weight.
# Use {biz} for business name, {trade} for trade, {state} for state name.
# The system rotates through these evenly (or by weight if specified).
SUBJECT_VARIANTS = [
    {
        "id": "A",
        "subject": "{biz} - I built you a free website mockup",
    },
    {
        "id": "B",
        "subject": "Quick question about {biz}'s website",
    },
    {
        "id": "C",
        "subject": "I noticed a few issues with your website, {biz}",
    },
]

# High-value trades (these get a scoring bonus in candidate selection)
HIGH_VALUE_TRADES = [
    "General Contractor", "Roofer", "HVAC", "Electrician", "Plumber",
    "Solar Installer", "Solar Panel Company", "Solar Energy Contractor",
]

# ─── Nano Banana (Google Gemini) Image Generation ──────────────────
# Get your API key at https://aistudio.google.com/apikey
GOOGLE_API_KEY = ""  # ← get your key at https://aistudio.google.com/apikey
IMAGE_MODEL = "gemini-2.5-flash-image"  # ~$0.04/image, fast
