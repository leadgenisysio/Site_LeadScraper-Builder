"""Generate premium tailored demo websites for contractor leads.

Uses scraped site content, AI-generated images (Nano Banana), and
trade-specific defaults to produce a high-quality standalone HTML page
that makes contractors say "WOW".
"""

import json
import logging
import random

from flask import render_template

from outreach.content_writer import enhance_site_content
from outreach.image_generator import (
    generate_about_image,
    generate_gallery_images,
    generate_hero_image,
    generate_logo,
    get_unsplash_urls,
    is_configured as images_configured,
)

logger = logging.getLogger(__name__)

# ─── SVG Icons (inline, no external deps) ────────────────────────────
# Each icon is a <path> inside a 24x24 viewBox.

SVG_ICONS = {
    "wrench": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
    "hammer": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 12-8.5 8.5c-.83.83-2.17.83-3 0 0 0 0 0 0 0a2.12 2.12 0 0 1 0-3L12 9"/><path d="M17.64 15 22 10.64"/><path d="m20.91 11.7-1.25-1.25c-.6-.6-.93-1.4-.93-2.25v-.86L16.01 4.6a5.56 5.56 0 0 0-3.94-1.64H9l.92.82A6.18 6.18 0 0 1 12 8.4v1.56l2 2h2.47l2.26 1.91"/></svg>',
    "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    "roof": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6"/></svg>',
    "bolt": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    "droplet": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/></svg>',
    "thermometer": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>',
    "brick": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="22" height="18" rx="2"/><line x1="1" y1="9" x2="23" y2="9"/><line x1="1" y1="15" x2="23" y2="15"/><line x1="12" y1="3" x2="12" y2="9"/><line x1="6" y1="9" x2="6" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/><line x1="12" y1="15" x2="12" y2="21"/></svg>',
    "paintbrush": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.37 2.63 14 7l-1.59-1.59a2 2 0 0 0-2.82 0L8 7l9 9 1.59-1.59a2 2 0 0 0 0-2.82L17 10l4.37-4.37a2.12 2.12 0 1 0-3-3Z"/><path d="M9 8c-2 3-4 3.5-7 4l8 10c2-1 6-5 6-7"/><path d="M14.5 17.5 4.5 15"/></svg>',
    "tree": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22v-7"/><path d="M17 8a5 5 0 0 0-10 0c0 6 10 6 10 0"/><path d="M15 13c2.5 0 5-1 5-5"/><path d="M9 13c-2.5 0-5-1-5-5"/></svg>',
    "leaf": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.9C15.5 4.9 20 8 20 8s3 4.5 1 10.5c-1.5 4-6 5.5-10 1.5"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>',
    "bug": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="6" width="8" height="14" rx="4"/><path d="m19 7-3 2"/><path d="m5 7 3 2"/><path d="m19 19-3-2"/><path d="m5 19 3-2"/><path d="M20 13h-4"/><path d="M4 13h4"/><path d="m10 4 1 2"/><path d="m14 4-1 2"/></svg>',
    "sparkles": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>',
    "sun": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
    "fence": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 3v18"/><path d="M12 3v18"/><path d="M20 3v18"/><path d="M2 9h20"/><path d="M2 15h20"/><path d="m4 3 2-2 2 2"/><path d="m12 3 2-2 2 2"/><path d="m20 3 2-2"/></svg>',
    "waves": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>',
    "truck": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/></svg>',
    "spray": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 10v7.64a2 2 0 0 1-.564 1.39l-1.844 1.9A.5.5 0 0 0 7.95 22h8.1a.5.5 0 0 0 .358-.85l-1.844-1.9A2 2 0 0 1 14 17.64V10"/><path d="M8.5 10h7"/><path d="M9.5 2h5"/><path d="M12 2v4"/><path d="M15 2a2.5 2.5 0 0 1 0 5"/><path d="M9 2a2.5 2.5 0 0 0 0 5"/></svg>',
    "layers": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
    "scissors": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>',
    "star": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    "star-empty": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
}

# Map trade → default icon key for service cards
TRADE_ICON_MAP = {
    "General Contractor": ["hammer", "home", "wrench", "layers", "shield", "sparkles"],
    "Roofer": ["roof", "hammer", "shield", "wrench", "home", "bolt"],
    "Electrician": ["bolt", "home", "wrench", "sun", "shield", "sparkles"],
    "Plumber": ["droplet", "wrench", "home", "shield", "thermometer", "sparkles"],
    "HVAC": ["thermometer", "wrench", "home", "shield", "bolt", "sparkles"],
    "Mason": ["brick", "hammer", "home", "shield", "wrench", "layers"],
    "Carpenter": ["hammer", "home", "wrench", "layers", "shield", "scissors"],
    "Painter": ["paintbrush", "home", "sparkles", "shield", "layers", "wrench"],
    "Landscaper": ["leaf", "tree", "home", "sparkles", "wrench", "sun"],
    "Lawn Care": ["leaf", "scissors", "sun", "sparkles", "shield", "wrench"],
    "Tree Service": ["tree", "leaf", "shield", "wrench", "truck", "sparkles"],
    "Pest Control": ["bug", "shield", "home", "sparkles", "wrench", "spray"],
    "Cleaning Service": ["sparkles", "home", "shield", "spray", "wrench", "star"],
    "Handyman": ["wrench", "hammer", "home", "bolt", "paintbrush", "shield"],
    "Solar Installer": ["sun", "bolt", "home", "shield", "wrench", "sparkles"],
    "Solar Panel Company": ["sun", "bolt", "home", "shield", "wrench", "sparkles"],
    "Solar Energy Contractor": ["sun", "bolt", "home", "shield", "wrench", "sparkles"],
    "Fencing Contractor": ["fence", "hammer", "wrench", "home", "shield", "sparkles"],
    "Pressure Washing": ["spray", "home", "sparkles", "wrench", "shield", "droplet"],
    "Pool Service": ["waves", "wrench", "sparkles", "shield", "thermometer", "droplet"],
    "Paving": ["layers", "truck", "wrench", "home", "shield", "hammer"],
}
_DEFAULT_ICONS = ["wrench", "home", "shield", "sparkles", "hammer", "bolt"]


# ─── Trade-specific service details (name + description) ─────────────

TRADE_SERVICE_DETAILS = {
    "General Contractor": [
        {"name": "Home Remodeling", "desc": "Complete interior and exterior renovations that transform your living space."},
        {"name": "Kitchen & Bath", "desc": "Custom kitchen and bathroom upgrades with premium finishes and fixtures."},
        {"name": "Room Additions", "desc": "Expand your home with seamlessly integrated new living spaces."},
        {"name": "Structural Repairs", "desc": "Foundation, framing, and load-bearing wall repairs done right."},
        {"name": "New Construction", "desc": "Ground-up custom homes built to your exact specifications."},
        {"name": "Basement Finishing", "desc": "Turn unused basement space into a beautiful living area."},
    ],
    "Roofer": [
        {"name": "Roof Replacement", "desc": "Complete tear-off and installation with premium materials and manufacturer warranties."},
        {"name": "Storm Damage Repair", "desc": "Fast response for hail, wind, and storm damage. We work directly with your insurance."},
        {"name": "Roof Inspections", "desc": "Detailed inspections with photo documentation and honest assessments."},
        {"name": "Gutter Installation", "desc": "Seamless gutters and downspouts to protect your home from water damage."},
        {"name": "Emergency Leak Repair", "desc": "24/7 emergency response to stop leaks and prevent further damage."},
        {"name": "Metal Roofing", "desc": "Durable, energy-efficient metal roofing that lasts 50+ years."},
    ],
    "Electrician": [
        {"name": "Panel Upgrades", "desc": "Modernize your electrical panel for safety, capacity, and code compliance."},
        {"name": "Wiring & Rewiring", "desc": "Complete residential wiring for new builds, remodels, and older homes."},
        {"name": "Lighting Design", "desc": "Custom lighting solutions from recessed LEDs to landscape illumination."},
        {"name": "Generator Installation", "desc": "Whole-home backup generators for uninterrupted power during outages."},
        {"name": "EV Charger Install", "desc": "Level 2 electric vehicle charger installation for your home garage."},
        {"name": "Smart Home Wiring", "desc": "Automated lighting, security, and smart device integration throughout your home."},
    ],
    "Plumber": [
        {"name": "Drain Cleaning", "desc": "Advanced hydro-jetting and camera inspection to clear any blockage."},
        {"name": "Water Heater Service", "desc": "Tank and tankless water heater installation, repair, and maintenance."},
        {"name": "Pipe Repair", "desc": "Trenchless pipe repair and replacement with minimal disruption to your property."},
        {"name": "Sewer Line Service", "desc": "Complete sewer line inspection, repair, and replacement services."},
        {"name": "Fixture Installation", "desc": "Professional installation of faucets, toilets, sinks, and showers."},
        {"name": "Emergency Plumbing", "desc": "24/7 emergency service for burst pipes, flooding, and urgent repairs."},
    ],
    "HVAC": [
        {"name": "AC Installation", "desc": "Energy-efficient central air and ductless systems sized perfectly for your home."},
        {"name": "Furnace Service", "desc": "Expert furnace installation, repair, and annual maintenance programs."},
        {"name": "Heat Pump Systems", "desc": "High-efficiency heat pumps for year-round comfort and energy savings."},
        {"name": "Ductwork", "desc": "Custom duct design, sealing, and replacement for optimal airflow."},
        {"name": "Indoor Air Quality", "desc": "Air purifiers, humidifiers, and filtration systems for healthier living."},
        {"name": "Maintenance Plans", "desc": "Preventive maintenance agreements that extend equipment life and reduce costs."},
    ],
    "Landscaper": [
        {"name": "Landscape Design", "desc": "Custom 3D landscape plans that bring your outdoor vision to life."},
        {"name": "Hardscaping", "desc": "Patios, walkways, retaining walls, and outdoor living spaces built to last."},
        {"name": "Garden & Plantings", "desc": "Curated plant selections for year-round color and low-maintenance beauty."},
        {"name": "Irrigation Systems", "desc": "Smart irrigation design and installation for efficient, automated watering."},
        {"name": "Outdoor Lighting", "desc": "Professional landscape lighting to highlight your home and improve safety."},
        {"name": "Sod Installation", "desc": "Premium sod installation with soil prep for an instant, lush lawn."},
    ],
    "Solar Installer": [
        {"name": "Solar Installation", "desc": "Custom-designed rooftop solar systems that maximize energy production."},
        {"name": "System Design", "desc": "Engineering and design optimized for your roof angle, shading, and usage."},
        {"name": "Battery Storage", "desc": "Home battery systems for energy independence and backup power."},
        {"name": "Panel Maintenance", "desc": "Professional cleaning and inspection to keep your system at peak output."},
        {"name": "Energy Audits", "desc": "Comprehensive home energy assessment to identify savings opportunities."},
        {"name": "Financing Options", "desc": "Flexible solar financing, leases, and PPA options to fit any budget."},
    ],
    "Painter": [
        {"name": "Interior Painting", "desc": "Flawless walls, ceilings, and trim with premium paints and clean edges."},
        {"name": "Exterior Painting", "desc": "Weather-resistant finishes that protect and beautify your home for years."},
        {"name": "Cabinet Painting", "desc": "Factory-quality cabinet refinishing at a fraction of replacement cost."},
        {"name": "Deck Staining", "desc": "Restore and protect your deck with professional-grade stains and sealers."},
        {"name": "Color Consultation", "desc": "Expert color guidance to find the perfect palette for your space."},
        {"name": "Commercial Painting", "desc": "Office, retail, and commercial painting with minimal business disruption."},
    ],
    "Lawn Care": [
        {"name": "Weekly Mowing", "desc": "Consistent, professional mowing with crisp edging and cleanup every visit."},
        {"name": "Fertilization", "desc": "Science-based fertilizer programs for a thick, green lawn year-round."},
        {"name": "Weed Control", "desc": "Targeted pre- and post-emergent treatments that eliminate weeds safely."},
        {"name": "Aeration & Seeding", "desc": "Core aeration and overseeding to thicken your lawn and improve soil."},
        {"name": "Seasonal Cleanup", "desc": "Comprehensive spring and fall cleanup including leaf removal and bed prep."},
        {"name": "Pest & Disease", "desc": "Lawn pest identification and treatment to keep your grass healthy."},
    ],
    "Tree Service": [
        {"name": "Tree Removal", "desc": "Safe, insured removal of any size tree with complete debris cleanup."},
        {"name": "Tree Trimming", "desc": "Expert pruning that improves health, safety, and curb appeal."},
        {"name": "Stump Grinding", "desc": "Complete stump removal below grade so you can reclaim your yard."},
        {"name": "Storm Cleanup", "desc": "Emergency response for fallen trees and storm damage, available 24/7."},
        {"name": "Tree Health", "desc": "ISA-certified arborist assessments for disease diagnosis and treatment."},
        {"name": "Land Clearing", "desc": "Efficient clearing for new construction, driveways, and landscaping."},
    ],
    "Pest Control": [
        {"name": "Termite Treatment", "desc": "Advanced liquid and bait systems that eliminate and prevent termite infestations."},
        {"name": "Rodent Control", "desc": "Humane trapping, exclusion, and prevention to keep rodents out for good."},
        {"name": "Ant & Spider Control", "desc": "Targeted interior and exterior treatments for ants, spiders, and crawling pests."},
        {"name": "Bed Bug Treatment", "desc": "Heat treatment and chemical solutions for complete bed bug elimination."},
        {"name": "Wildlife Removal", "desc": "Humane removal of raccoons, squirrels, bats, and other wildlife intruders."},
        {"name": "Preventive Plans", "desc": "Quarterly treatments that create a protective barrier around your home."},
    ],
    "Cleaning Service": [
        {"name": "Deep Cleaning", "desc": "Top-to-bottom deep cleaning that reaches every corner and surface."},
        {"name": "Regular Service", "desc": "Weekly, bi-weekly, or monthly visits to keep your home consistently spotless."},
        {"name": "Move-In/Move-Out", "desc": "Thorough cleaning that gets every space ready for the next chapter."},
        {"name": "Office Cleaning", "desc": "Professional office and commercial cleaning for a healthier workspace."},
        {"name": "Post-Construction", "desc": "Specialized cleanup of construction dust, debris, and residue."},
        {"name": "Window Cleaning", "desc": "Streak-free interior and exterior window cleaning for crystal clarity."},
    ],
    "Handyman": [
        {"name": "General Repairs", "desc": "Fix anything around the house — no job too small, no repair too tricky."},
        {"name": "Furniture Assembly", "desc": "Expert assembly of furniture, shelving, and storage systems."},
        {"name": "Drywall Repair", "desc": "Seamless drywall patching, texturing, and finishing that's invisible."},
        {"name": "Door & Window", "desc": "Installation, adjustment, and repair of interior and exterior doors and windows."},
        {"name": "Pressure Washing", "desc": "Revitalize driveways, siding, decks, and fences with professional washing."},
        {"name": "Mounting & Install", "desc": "TV mounting, shelving, fixtures, and smart home device installation."},
    ],
    "Fencing Contractor": [
        {"name": "Wood Fencing", "desc": "Custom cedar and pressure-treated wood fences built for beauty and durability."},
        {"name": "Vinyl Fencing", "desc": "Maintenance-free vinyl privacy and picket fences in multiple styles."},
        {"name": "Chain Link", "desc": "Durable chain link fencing for security, pet containment, and property lines."},
        {"name": "Fence Repair", "desc": "Fast, reliable repair of leaning, broken, or storm-damaged fencing."},
        {"name": "Gate Installation", "desc": "Custom swing and sliding gates with optional automatic openers."},
        {"name": "Iron & Aluminum", "desc": "Elegant ornamental iron and aluminum fencing for upscale properties."},
    ],
    "Pressure Washing": [
        {"name": "House Washing", "desc": "Safe soft-wash technique that removes years of grime without damage."},
        {"name": "Driveway Cleaning", "desc": "Restore concrete and pavers to like-new condition with surface cleaning."},
        {"name": "Deck Restoration", "desc": "Strip old stain, clean wood fibers, and prep for a fresh finish."},
        {"name": "Roof Soft Wash", "desc": "Gentle roof cleaning that kills algae and moss without shingle damage."},
        {"name": "Commercial Cleaning", "desc": "Storefronts, parking lots, and building exteriors at any scale."},
        {"name": "Fence Cleaning", "desc": "Bring weathered fences back to life with targeted pressure washing."},
    ],
    "Pool Service": [
        {"name": "Pool Cleaning", "desc": "Weekly or bi-weekly cleaning including skimming, vacuuming, and brushing."},
        {"name": "Chemical Balancing", "desc": "Precise water chemistry management for safe, crystal-clear water."},
        {"name": "Equipment Repair", "desc": "Pump, filter, heater, and automation system diagnosis and repair."},
        {"name": "Opening & Closing", "desc": "Seasonal pool opening and winterization done by certified technicians."},
        {"name": "Liner Replacement", "desc": "Vinyl liner measurement, custom ordering, and professional installation."},
        {"name": "Renovation", "desc": "Complete pool resurfacing, tile replacement, and equipment upgrades."},
    ],
}

_DEFAULT_SERVICE_DETAILS = [
    {"name": "Professional Service", "desc": "Expert solutions tailored to your specific needs and budget."},
    {"name": "Quality Workmanship", "desc": "Meticulous attention to detail on every project we complete."},
    {"name": "Free Estimates", "desc": "Transparent, no-obligation quotes with upfront pricing."},
    {"name": "Licensed & Insured", "desc": "Fully licensed and insured for your complete peace of mind."},
    {"name": "Emergency Service", "desc": "Rapid response when you need help the most, day or night."},
    {"name": "Satisfaction Guaranteed", "desc": "We stand behind our work with a 100% satisfaction guarantee."},
]


# ─── Trade testimonials ──────────────────────────────────────────────

TRADE_TESTIMONIALS = {
    "General Contractor": [
        {"name": "Michael R.", "text": "They completely transformed our outdated kitchen into a modern showpiece. Every detail was perfect and the project finished on schedule.", "rating": 5, "project": "Kitchen Remodel"},
        {"name": "Sarah P.", "text": "Adding a master suite seemed overwhelming until this team made it effortless. The craftsmanship is outstanding.", "rating": 5, "project": "Room Addition"},
        {"name": "David & Lisa K.", "text": "From permits to final walkthrough, they handled everything professionally. Our basement is now our favorite room.", "rating": 5, "project": "Basement Finishing"},
    ],
    "Roofer": [
        {"name": "Jennifer M.", "text": "They replaced our entire roof in two days. The crew was professional, cleanup was spotless, and it looks incredible.", "rating": 5, "project": "Full Roof Replacement"},
        {"name": "Tom H.", "text": "After the hailstorm, they were the first to respond and handled everything with our insurance. Couldn't be happier.", "rating": 5, "project": "Storm Damage Repair"},
        {"name": "Karen W.", "text": "Best roofing company we've ever worked with. Fair pricing, quality materials, and they stand behind their work.", "rating": 5, "project": "Roof Inspection & Repair"},
    ],
    "Electrician": [
        {"name": "Robert S.", "text": "Upgraded our entire panel and added circuits for the workshop. Clean work, passed inspection first time.", "rating": 5, "project": "Panel Upgrade"},
        {"name": "Amanda L.", "text": "The recessed lighting transformed our living room. They helped us pick the perfect layout and color temperature.", "rating": 5, "project": "Lighting Installation"},
        {"name": "Chris B.", "text": "Had them install a whole-home generator. When the power went out last month, we were the only house on the block with lights.", "rating": 5, "project": "Generator Install"},
    ],
    "Plumber": [
        {"name": "Nancy D.", "text": "Fixed a slab leak without tearing up our floors. These guys know what they're doing and saved us thousands.", "rating": 5, "project": "Leak Repair"},
        {"name": "Steve M.", "text": "Installed a tankless water heater and the difference is night and day. Endless hot water and lower bills.", "rating": 5, "project": "Water Heater Install"},
        {"name": "Linda G.", "text": "Emergency call at 11pm and they were at our door in 30 minutes. Stopped the flooding and fixed it right.", "rating": 5, "project": "Emergency Service"},
    ],
    "HVAC": [
        {"name": "Mark T.", "text": "New AC system works perfectly. Our energy bill dropped 40% the first month. Should have done this years ago.", "rating": 5, "project": "AC Installation"},
        {"name": "Barbara N.", "text": "Their maintenance plan caught a problem before it became expensive. Honest, thorough, and fairly priced.", "rating": 5, "project": "Maintenance Plan"},
        {"name": "John P.", "text": "Installed a mini-split in our sunroom that used to be unbearable in summer. Now it's our favorite room.", "rating": 5, "project": "Ductless System"},
    ],
    "Landscaper": [
        {"name": "Patricia F.", "text": "They designed and installed our entire backyard — patio, plantings, irrigation, lighting. It's like a resort.", "rating": 5, "project": "Full Landscape Design"},
        {"name": "Richard H.", "text": "The retaining wall and paver patio transformed a muddy hillside into a beautiful outdoor living space.", "rating": 5, "project": "Hardscaping"},
        {"name": "Emily C.", "text": "Our front yard went from embarrassing to the best on the street. Neighbors keep asking who did the work.", "rating": 5, "project": "Front Yard Redesign"},
    ],
    "Solar Installer": [
        {"name": "Greg A.", "text": "Our electric bill went from $280/month to $12. The system paid for itself faster than they estimated.", "rating": 5, "project": "Residential Solar"},
        {"name": "Michelle R.", "text": "They handled everything — design, permits, installation, and utility coordination. We just watched the savings roll in.", "rating": 5, "project": "System Install"},
        {"name": "Daniel W.", "text": "Added battery storage last year and now we're completely energy independent. Best investment we've ever made.", "rating": 5, "project": "Solar + Battery"},
    ],
    "Painter": [
        {"name": "Catherine L.", "text": "They painted our entire interior in 3 days with zero mess. The edges are so clean it looks factory-sprayed.", "rating": 5, "project": "Interior Painting"},
        {"name": "Andrew J.", "text": "Our house exterior went from faded to stunning. They even fixed some siding issues they found during prep.", "rating": 5, "project": "Exterior Painting"},
        {"name": "Rachel M.", "text": "Had our kitchen cabinets painted instead of replaced — saved us $15,000 and they look brand new.", "rating": 5, "project": "Cabinet Painting"},
    ],
}

_DEFAULT_TESTIMONIALS = [
    {"name": "Michael R.", "text": "Outstanding work from start to finish. Professional, on time, and the results exceeded our expectations.", "rating": 5, "project": "Home Project"},
    {"name": "Sarah K.", "text": "They were the most professional team we've worked with. Fair pricing and incredible attention to detail.", "rating": 5, "project": "Service Call"},
    {"name": "David L.", "text": "Highly recommend! They did exactly what they promised, finished on schedule, and left everything spotless.", "rating": 5, "project": "Full Service"},
]


# ─── Trade process steps ─────────────────────────────────────────────

TRADE_PROCESS_STEPS = {
    "General Contractor": [
        {"step": "1", "title": "Free Consultation", "desc": "We visit your home, listen to your vision, and provide a detailed estimate — no pressure, no obligation."},
        {"step": "2", "title": "Design & Planning", "desc": "Our team creates a clear project plan with timelines, materials, and permits handled for you."},
        {"step": "3", "title": "Expert Build", "desc": "Our skilled crews deliver quality craftsmanship with daily updates and a clean job site."},
    ],
    "Roofer": [
        {"step": "1", "title": "Free Inspection", "desc": "We thoroughly inspect your roof with photos and provide an honest, detailed assessment."},
        {"step": "2", "title": "Expert Installation", "desc": "Our certified crew handles everything — permits, materials, installation, and full cleanup."},
        {"step": "3", "title": "Final Walkthrough", "desc": "We walk through every detail together and back it all with our written warranty."},
    ],
    "Electrician": [
        {"step": "1", "title": "Assessment", "desc": "We evaluate your electrical needs, check for code issues, and provide upfront pricing."},
        {"step": "2", "title": "Professional Work", "desc": "Licensed electricians complete all work to code with clean, organized installations."},
        {"step": "3", "title": "Inspection & Testing", "desc": "Every job is tested, inspected, and guaranteed to meet or exceed electrical codes."},
    ],
    "Plumber": [
        {"step": "1", "title": "Diagnose", "desc": "We identify the problem quickly using camera inspections and advanced diagnostics."},
        {"step": "2", "title": "Repair Right", "desc": "Our licensed plumbers fix it right the first time using quality parts and proven methods."},
        {"step": "3", "title": "Guaranteed", "desc": "Every repair comes with our satisfaction guarantee and a clear warranty on parts and labor."},
    ],
    "HVAC": [
        {"step": "1", "title": "Home Assessment", "desc": "We calculate your exact heating and cooling needs with a Manual J load calculation."},
        {"step": "2", "title": "Custom Solution", "desc": "We recommend the best equipment for your home, budget, and efficiency goals."},
        {"step": "3", "title": "Expert Install", "desc": "Factory-trained technicians install your system and ensure perfect performance."},
    ],
    "Landscaper": [
        {"step": "1", "title": "Design Session", "desc": "We walk your property together and create a custom landscape plan with 3D visualization."},
        {"step": "2", "title": "Build & Plant", "desc": "Our crews bring the design to life with quality materials and expert installation."},
        {"step": "3", "title": "Enjoy & Maintain", "desc": "Your dream landscape is complete, with optional maintenance plans to keep it perfect."},
    ],
    "Solar Installer": [
        {"step": "1", "title": "Free Solar Assessment", "desc": "We analyze your roof, energy usage, and local incentives to design the perfect system."},
        {"step": "2", "title": "Permitting & Install", "desc": "We handle all paperwork, permits, and installation — you don't lift a finger."},
        {"step": "3", "title": "Power On", "desc": "Your system goes live and you start saving from day one, with monitoring included."},
    ],
}

_DEFAULT_PROCESS_STEPS = [
    {"step": "1", "title": "Free Estimate", "desc": "Contact us for a no-obligation quote. We'll assess your needs and provide transparent pricing."},
    {"step": "2", "title": "Quality Work", "desc": "Our experienced team completes the job with attention to detail and clean workmanship."},
    {"step": "3", "title": "100% Satisfaction", "desc": "We're not done until you're completely happy. Every project is backed by our guarantee."},
]


# ─── Trade stats ─────────────────────────────────────────────────────

TRADE_STATS = {
    "General Contractor": [
        {"value": "500+", "label": "Projects Completed"},
        {"value": "15+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "100%", "label": "Licensed & Insured"},
    ],
    "Roofer": [
        {"value": "1,200+", "label": "Roofs Completed"},
        {"value": "20+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "100%", "label": "Satisfaction Rate"},
    ],
    "Electrician": [
        {"value": "3,000+", "label": "Jobs Completed"},
        {"value": "15+", "label": "Years Licensed"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "24/7", "label": "Emergency Service"},
    ],
    "Plumber": [
        {"value": "5,000+", "label": "Service Calls"},
        {"value": "18+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "24/7", "label": "Emergency Service"},
    ],
    "HVAC": [
        {"value": "2,500+", "label": "Systems Installed"},
        {"value": "20+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "98%", "label": "First-Call Fix Rate"},
    ],
    "Landscaper": [
        {"value": "800+", "label": "Properties Designed"},
        {"value": "12+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "100%", "label": "Satisfaction Rate"},
    ],
    "Solar Installer": [
        {"value": "1,500+", "label": "Systems Installed"},
        {"value": "10+", "label": "Years Experience"},
        {"value": "5.0", "label": "Star Rating", "is_stars": True},
        {"value": "$0", "label": "Avg Electric Bill"},
    ],
}

_DEFAULT_STATS = [
    {"value": "500+", "label": "Projects Completed"},
    {"value": "15+", "label": "Years Experience"},
    {"value": "5.0", "label": "Star Rating", "is_stars": True},
    {"value": "100%", "label": "Satisfaction Guaranteed"},
]


# ─── Trade headlines ─────────────────────────────────────────────────

TRADE_HEADLINES = {
    "General Contractor": "Building Your Dream Home,\nOne Detail at a Time",
    "Roofer": "Protecting What Matters Most\u2014Starting From the Top",
    "Electrician": "Powering Your Home With\nSafety & Precision",
    "Plumber": "Expert Plumbing Solutions\nWhen You Need Them Most",
    "HVAC": "Year-Round Comfort\nYou Can Count On",
    "Mason": "Timeless Masonry\nBuilt to Last Generations",
    "Carpenter": "Custom Craftsmanship\nThat Brings Your Vision to Life",
    "Painter": "Transforming Spaces\nWith a Perfect Finish",
    "Siding Contractor": "Beautiful Siding That\nProtects & Impresses",
    "Flooring Contractor": "Stunning Floors That\nTransform Every Room",
    "Landscaper": "Outdoor Spaces\nDesigned to Inspire",
    "Lawn Care": "A Lawn That Makes\nYour Neighbors Jealous",
    "Tree Service": "Professional Tree Care\nYou Can Trust",
    "Pest Control": "Protecting Your Home\nFrom Unwanted Guests",
    "Cleaning Service": "A Spotless Home\nWithout Lifting a Finger",
    "Handyman": "No Job Too Small\u2014We Fix It All",
    "Solar Installer": "Harness the Sun.\nSlash Your Bills.",
    "Solar Panel Company": "Go Solar.\nStart Saving Today.",
    "Solar Energy Contractor": "Clean Energy.\nSmarter Living.",
    "Pool Service": "Crystal Clear Pools,\nEvery Single Day",
    "Fencing Contractor": "Beautiful Fencing That\nStands the Test of Time",
    "Pressure Washing": "Restore Your Property's\nCurb Appeal Instantly",
    "Paving": "Smooth, Durable Surfaces\nThat Make a Statement",
}


# ─── Trade colors ────────────────────────────────────────────────────

TRADE_COLORS = {
    "Roofer": "#b91c1c",
    "Electrician": "#d97706",
    "Plumber": "#2563eb",
    "HVAC": "#0891b2",
    "General Contractor": "#1e40af",
    "Mason": "#92400e",
    "Carpenter": "#854d0e",
    "Painter": "#7c3aed",
    "Solar Installer": "#ea580c",
    "Solar Panel Company": "#ea580c",
    "Solar Energy Contractor": "#ea580c",
    "Landscaper": "#15803d",
    "Lawn Care": "#16a34a",
    "Tree Service": "#166534",
    "Pest Control": "#dc2626",
    "Cleaning Service": "#0d9488",
    "Handyman": "#ca8a04",
    "Pool Service": "#0284c7",
    "Fencing Contractor": "#78350f",
    "Pressure Washing": "#0369a1",
    "Paving": "#525252",
}


# ── Trade-Specific FAQs ──────────────────────────────────────────────

_DEFAULT_FAQS = [
    {"q": "Do you offer free estimates?", "a": "Absolutely! We provide free, no-obligation estimates for all projects. Just give us a call or fill out our contact form and we'll schedule a convenient time to assess your needs."},
    {"q": "Are you licensed and insured?", "a": "Yes, we are fully licensed, bonded, and insured. We carry comprehensive liability insurance and workers' compensation coverage for your complete peace of mind."},
    {"q": "What areas do you serve?", "a": "We proudly serve the local area and surrounding communities. Contact us to confirm we cover your specific location — we're happy to discuss your project regardless."},
    {"q": "How long does a typical project take?", "a": "Project timelines vary depending on scope and complexity. During your free estimate, we'll provide a detailed timeline so you know exactly what to expect from start to finish."},
]

TRADE_FAQS = {
    "Roofer": [
        {"q": "How long does a roof replacement take?", "a": "Most residential roof replacements are completed in 1-3 days, depending on the size and complexity of your roof. We'll provide an exact timeline during your free inspection."},
        {"q": "Do you work with insurance claims?", "a": "Yes! We have extensive experience working with insurance companies on storm damage claims. We'll help document the damage, meet with your adjuster, and handle the paperwork to make the process as smooth as possible."},
        {"q": "What type of roofing materials do you use?", "a": "We offer a full range of materials including architectural shingles, metal roofing, tile, and flat roof systems. We'll help you choose the best option for your home, budget, and climate."},
        {"q": "Do you offer a warranty on your work?", "a": "Absolutely. We provide a workmanship warranty on all installations in addition to the manufacturer's material warranty. Ask us about our specific warranty terms during your estimate."},
    ],
    "Plumber": [
        {"q": "Do you offer emergency plumbing services?", "a": "Yes, we provide 24/7 emergency plumbing services. Whether it's a burst pipe, major leak, or backed-up sewer line, we'll be there fast to minimize damage to your home."},
        {"q": "How much does a plumbing repair typically cost?", "a": "Costs vary depending on the issue, but we always provide upfront pricing before any work begins. No surprises, no hidden fees — just honest, fair pricing."},
        {"q": "Can you help with bathroom or kitchen remodeling?", "a": "Absolutely! We handle all plumbing aspects of remodeling projects including fixture installation, pipe rerouting, and connecting new appliances."},
        {"q": "Do you offer water heater installation?", "a": "Yes, we install and service all types of water heaters including traditional tank, tankless, and hybrid models. We can help you choose the most energy-efficient option for your home."},
    ],
    "Electrician": [
        {"q": "Can you upgrade my electrical panel?", "a": "Yes, panel upgrades are one of our specialties. If your home has an outdated or undersized panel, we can upgrade it to meet modern safety standards and handle increased electrical demands."},
        {"q": "Do you install EV charging stations?", "a": "Absolutely! We're certified to install Level 2 EV charging stations for all major electric vehicle brands. We'll handle the wiring, dedicated circuit, and permitting."},
        {"q": "How do I know if my home needs rewiring?", "a": "Common signs include frequently tripped breakers, flickering lights, warm outlets, or a home built before 1970. We offer free electrical safety inspections to assess your system."},
        {"q": "Do you handle commercial electrical work?", "a": "Yes, we serve both residential and commercial clients. From office build-outs to retail lighting to industrial installations, we have the expertise and licensing to handle it all."},
    ],
    "HVAC": [
        {"q": "How often should I service my HVAC system?", "a": "We recommend professional maintenance twice a year — once in spring for your AC and once in fall for your heating system. Regular maintenance extends equipment life and prevents costly breakdowns."},
        {"q": "What size AC unit does my home need?", "a": "Proper sizing depends on your home's square footage, insulation, window placement, and other factors. We perform a detailed load calculation to recommend the perfect size — oversized or undersized units waste energy and money."},
        {"q": "Do you offer financing for new HVAC systems?", "a": "Yes, we offer flexible financing options to make new system installations affordable. Ask us about our current promotions and monthly payment plans."},
        {"q": "How long does a new AC installation take?", "a": "A standard residential AC installation is typically completed in one day. More complex installations involving ductwork modifications may take 2-3 days."},
    ],
    "General Contractor": [
        {"q": "What types of projects do you handle?", "a": "We handle everything from kitchen and bathroom renovations to room additions, whole-home remodels, and new construction. No project is too big or too small for our experienced team."},
        {"q": "Do you handle permits and inspections?", "a": "Yes, we manage the entire permitting process from application to final inspection. We know the local building codes inside and out and ensure your project is fully compliant."},
        {"q": "How do you handle project changes or additions?", "a": "Changes happen — we get it. We use a formal change order process that clearly documents scope changes, cost adjustments, and timeline impacts before any additional work begins."},
        {"q": "Can I see examples of your previous work?", "a": "Absolutely! Check out our portfolio section above, and we're happy to provide references from past clients. We take pride in our work and love showing it off."},
    ],
    "Solar Installer": [
        {"q": "How much can I save with solar panels?", "a": "Most homeowners save 50-90% on their electricity bills with solar. The exact savings depend on your roof size, energy usage, and local utility rates. We provide a free savings analysis with every estimate."},
        {"q": "Do solar panels work on cloudy days?", "a": "Yes! Solar panels still generate electricity on cloudy days, just at a reduced rate. Modern panels are much more efficient than older technology and perform well in various weather conditions."},
        {"q": "What financing options are available for solar?", "a": "We offer multiple financing options including $0-down loans, leases, and PPAs. Plus, the federal solar tax credit can save you 30% on your system cost. We'll help you find the best option."},
        {"q": "How long do solar panels last?", "a": "Quality solar panels are warrantied for 25 years and can last 30-40+ years. They require virtually no maintenance and continue producing clean energy decade after decade."},
    ],
    "Landscaper": [
        {"q": "Do you offer landscape design services?", "a": "Yes! We provide full landscape design including 3D renderings so you can visualize your project before we break ground. Our designers work with you to create a plan that matches your vision and budget."},
        {"q": "Do you maintain landscapes after installation?", "a": "Absolutely. We offer ongoing maintenance programs including mowing, pruning, fertilization, and seasonal cleanups to keep your landscape looking its best year-round."},
        {"q": "What's the best time of year for landscaping?", "a": "Spring and fall are ideal for most landscaping projects, but we work year-round. Hardscaping projects like patios and walkways can be done in any season, and we can plant trees throughout the growing season."},
        {"q": "Do you install irrigation systems?", "a": "Yes, we design and install complete irrigation systems including smart controllers that adjust watering based on weather conditions. Proper irrigation saves water and keeps your landscape thriving."},
    ],
}


# ─── Helpers ─────────────────────────────────────────────────────────

def _parse_site_content(lead):
    """Parse site_content from a lead dict, handling JSON strings."""
    sc = lead.get("site_content")
    if isinstance(sc, str):
        try:
            sc = json.loads(sc)
        except (json.JSONDecodeError, TypeError):
            sc = {}
    return sc or {}


def _get_services(lead, site_content, trade):
    """Get service details list — prefer scraped with descriptions, fall back to defaults."""
    # Best case: scraped services WITH descriptions
    if site_content.get("services_with_desc"):
        scraped = site_content["services_with_desc"]
        if len(scraped) >= 3:
            result = []
            for s in scraped[:6]:
                name = s.get("name", "")
                desc = s.get("desc", "")
                if not desc:
                    desc = "Professional service delivered with quality and care."
                result.append({"name": name, "desc": desc})
            return result

    # Good case: scraped service names (pair with trade-default descriptions)
    if site_content.get("services_list"):
        scraped = site_content["services_list"]
        if len(scraped) >= 3:
            defaults = TRADE_SERVICE_DETAILS.get(trade, _DEFAULT_SERVICE_DETAILS)
            desc_map = {d["name"].lower(): d["desc"] for d in defaults}
            result = []
            for s in scraped[:6]:
                desc = desc_map.get(s.lower(), "Professional service delivered with quality and care.")
                result.append({"name": s, "desc": desc})
            return result

    # Fallback: trade-specific defaults
    return TRADE_SERVICE_DETAILS.get(trade, _DEFAULT_SERVICE_DETAILS)[:6]


def _get_about_text(lead, site_content, trade):
    """Get about text — prefer scraped, fall back to generic."""
    if site_content.get("about_text"):
        return site_content["about_text"]
    biz = lead.get("business_name", "Our company")
    return (
        f"{biz} is a trusted name in {trade.lower()} services, proudly serving "
        f"the local community. We are fully licensed, insured, and committed to "
        f"delivering exceptional workmanship on every project. Our experienced "
        f"team takes pride in customer satisfaction and stands behind every job "
        f"we complete."
    )


def _get_primary_color(lead, site_content, trade):
    """Get brand color — prefer scraped, fall back to trade default."""
    if site_content.get("primary_color"):
        return site_content["primary_color"]
    return TRADE_COLORS.get(trade, "#2563eb")


def _get_headline(lead, site_content, trade):
    """Get hero headline — prefer scraped tagline, fall back to trade default."""
    if site_content.get("tagline"):
        tagline = site_content["tagline"]
        if 10 < len(tagline) < 120:
            return tagline
    return TRADE_HEADLINES.get(trade, "Professional Service\nYou Can Trust")


def _get_testimonials(site_content, trade):
    """Get testimonials — prefer scraped, fall back to trade defaults."""
    if site_content.get("testimonials"):
        scraped = site_content["testimonials"]
        if len(scraped) >= 2:
            # Normalize to template format
            result = []
            for t in scraped[:3]:
                result.append({
                    "name": t.get("name", "Happy Customer"),
                    "text": t.get("text", ""),
                    "rating": t.get("rating", 5),
                    "project": "",  # Scraped reviews don't always have project type
                })
            return result
    return TRADE_TESTIMONIALS.get(trade, _DEFAULT_TESTIMONIALS)[:3]


def _get_icons(trade):
    """Get list of SVG icon keys for a trade."""
    keys = TRADE_ICON_MAP.get(trade, _DEFAULT_ICONS)
    return [SVG_ICONS.get(k, SVG_ICONS["wrench"]) for k in keys]


# ─── Main Generator ──────────────────────────────────────────────────

def generate_demo_site(lead):
    """Generate a premium demo website for a lead.

    Parameters
    ----------
    lead : dict
        A lead record from the database.

    Returns
    -------
    dict
        ``{"html": str, "images": dict[str, bytes]}`` where images maps
        filenames (e.g. ``"hero.jpg"``) to raw bytes for Netlify deploy.
    """
    site_content = _parse_site_content(lead)

    business_name = lead.get("business_name", "Your Business")
    trade = lead.get("trade", "Contractor")
    phone = lead.get("phone", "")
    email = lead.get("email", "")
    state = lead.get("state", "")

    # Get first phone/email if multiple
    if phone and "," in phone:
        phone = phone.split(",")[0].strip()
    if email and "," in email:
        email = email.split(",")[0].strip()

    primary_color = _get_primary_color(lead, site_content, trade)
    headline = _get_headline(lead, site_content, trade)
    services = _get_services(lead, site_content, trade)
    about_text = _get_about_text(lead, site_content, trade)
    service_area = site_content.get("service_area", "")
    years_in_business = site_content.get("years_in_business", "")
    testimonials = _get_testimonials(site_content, trade)
    process_steps = TRADE_PROCESS_STEPS.get(trade, _DEFAULT_PROCESS_STEPS)[:3]
    stats = TRADE_STATS.get(trade, _DEFAULT_STATS)[:4]
    service_icons = _get_icons(trade)
    meta_description = ""
    cta_text = ""

    # ── AI Content Enhancement (Prompt Injection) ────────────────────
    ai_content = enhance_site_content(
        business_name=business_name,
        trade=trade,
        state=state,
        scraped_about=about_text,
        scraped_services=services,
        scraped_tagline=headline,
        service_area=service_area,
        years_in_business=years_in_business,
    )

    if ai_content:
        logger.info("AI content enhancement applied for %s", business_name)
        # Override with AI-generated content (keeps scraped data as fallback)
        if ai_content.get("headline"):
            headline = ai_content["headline"]
        if ai_content.get("about_text"):
            about_text = ai_content["about_text"]
        if ai_content.get("service_descriptions") and len(ai_content["service_descriptions"]) >= 4:
            services = ai_content["service_descriptions"][:6]
        if ai_content.get("meta_description"):
            meta_description = ai_content["meta_description"]
        if ai_content.get("cta_text"):
            cta_text = ai_content["cta_text"]

    # ── Scraped images from their existing site ─────────────────────────
    scraped_gallery = site_content.get("gallery_images", [])
    has_scraped_gallery = len(scraped_gallery) >= 2

    # ── Generate or fetch images ──────────────────────────────────────
    images = {}  # filename → bytes (for Netlify deploy)
    logo_url = ""
    hero_url = ""
    about_url = ""
    gallery_urls = []

    # ── Logo: scraped > AI-generated > monogram fallback ────────────
    scraped_logo = site_content.get("logo_url", "")
    if scraped_logo:
        logo_url = scraped_logo
        logger.info("Using scraped logo from their site: %s", scraped_logo[:60])
    elif images_configured():
        logo_bytes = generate_logo(trade, business_name)
        if logo_bytes:
            images["logo.png"] = logo_bytes
            logo_url = "./img/logo.png"
            logger.info("AI logo generated for %s", business_name)

    if images_configured():
        logger.info("Generating AI images for %s (%s)", business_name, trade)

        # Hero: use first scraped gallery image if large enough, else AI-generate
        if has_scraped_gallery and len(scraped_gallery) >= 4:
            # They have enough photos — use first as hero (external URL)
            hero_url = scraped_gallery[0]
            logger.info("Using scraped photo as hero image")
        else:
            hero_bytes = generate_hero_image(trade, business_name, service_area)
            if hero_bytes:
                images["hero.jpg"] = hero_bytes
                hero_url = "./img/hero.jpg"

        # About: use second scraped gallery image if available, else AI-generate
        if has_scraped_gallery and len(scraped_gallery) >= 3:
            about_url = scraped_gallery[1]
            logger.info("Using scraped photo as about image")
        else:
            about_bytes = generate_about_image(trade, business_name)
            if about_bytes:
                images["about.jpg"] = about_bytes
                about_url = "./img/about.jpg"

        # Gallery: use remaining scraped photos, backfill with AI-generated
        if has_scraped_gallery:
            # Skip photos used for hero/about (first 2), use rest for gallery
            start_idx = 2 if len(scraped_gallery) >= 4 else 0
            gallery_urls = scraped_gallery[start_idx:start_idx + 6]
            logger.info("Using %d scraped gallery images from their site", len(gallery_urls))
            # If we still need more, AI-generate extras
            needed = max(0, 4 - len(gallery_urls))
            if needed > 0:
                gallery_list = generate_gallery_images(trade, count=needed)
                for i, img in enumerate(gallery_list):
                    if img:
                        fname = f"gallery-{i+1}.jpg"
                        images[fname] = img
                        gallery_urls.append(f"./img/{fname}")
        else:
            gallery_list = generate_gallery_images(trade, count=4)
            for i, img in enumerate(gallery_list):
                if img:
                    images[f"gallery-{i+1}.jpg"] = img
            gallery_urls = [f"./img/gallery-{i+1}.jpg" for i in range(len(gallery_list)) if gallery_list[i]]
    else:
        # No AI image API configured — use Unsplash + scraped photos
        logger.info("Using Unsplash fallbacks for %s (%s)", business_name, trade)
        urls = get_unsplash_urls(trade)
        hero_url = scraped_gallery[0] if len(scraped_gallery) >= 4 else urls["hero"]
        about_url = scraped_gallery[1] if len(scraped_gallery) >= 3 else urls["about"]
        if has_scraped_gallery:
            start_idx = 2 if len(scraped_gallery) >= 4 else 0
            gallery_urls = scraped_gallery[start_idx:start_idx + 6]
        else:
            gallery_urls = urls["gallery"][:4]

    # ── Build trust/credibility elements for contact section ──────────
    trust_points = [
        "Licensed & Insured",
        "Free Estimates",
        "Satisfaction Guaranteed",
    ]
    if years_in_business:
        trust_points.insert(0, f"{years_in_business} Years of Experience"
                            if not str(years_in_business).endswith("years")
                            else f"{years_in_business} of Experience")
    if service_area:
        trust_points.append(f"Serving {service_area}")

    # ── FAQs ─────────────────────────────────────────────────────────
    faqs = TRADE_FAQS.get(trade, _DEFAULT_FAQS)[:4]

    # ── Layout variant (1=Modern, 2=Bold Dark, 3=Elegant Warm) ───────
    layout = random.choice([1, 2, 3])
    logger.info("Using layout variant %d for %s", layout, business_name)

    # ── Render template ───────────────────────────────────────────────
    html = render_template(
        "demo_site/contractor.html",
        business_name=business_name,
        trade=trade,
        phone=phone,
        email=email,
        state=state,
        headline=headline,
        services=services,
        about_text=about_text,
        primary_color=primary_color,
        service_area=service_area,
        years_in_business=years_in_business,
        testimonials=testimonials,
        process_steps=process_steps,
        stats=stats,
        service_icons=service_icons,
        hero_url=hero_url,
        about_url=about_url,
        gallery_urls=gallery_urls,
        logo_url=logo_url,
        trust_points=trust_points,
        faqs=faqs,
        layout=layout,
        meta_description=meta_description,
        cta_text=cta_text,
    )

    return {"html": html, "images": images}
