"""
Run once before your demo: `python seed_data.py`

Populates districts, categories, three demo accounts, a handful of sample
knowledge records (with real locally-computed embeddings, so semantic
search and Ask LOKVAANI AI work immediately), and risk assessments for the
Knowledge Risk Dashboard. Safe to re-run - it skips anything already there.
"""
import json

from werkzeug.security import generate_password_hash

from app import create_app
from database import get_db
from services.ai_pipeline import embed_text
from services.risk import compute_risk
from utils import slugify, next_knowledge_id

DISTRICTS = [
    ("Almora", "Known for terraced hillside farming and traditional woodcraft."),
    ("Bageshwar", "River-valley communities with strong oral storytelling traditions."),
    ("Chamoli", "High-altitude villages near the Nanda Devi range."),
    ("Champawat", "Historic Kumaoni region with early stone architecture."),
    ("Dehradun", "Doon valley, home to diverse migrant and local knowledge traditions."),
    ("Haridwar", "Ganga-plain communities with river-based livelihoods."),
    ("Nainital", "Lake district with mixed hill-farming and craft traditions."),
    ("Pauri Garhwal", "Terraced Garhwali villages known for wool weaving."),
    ("Pithoragarh", "Border district with Bhotiya community textile and trade knowledge."),
    ("Rudraprayag", "Confluence town with pilgrimage-linked traditional trades."),
    ("Tehri Garhwal", "Reservoir region known for seed preservation practices."),
    ("Udham Singh Nagar", "Plains district with Terai agricultural knowledge."),
    ("Uttarkashi", "Upper Himalayan valleys with traditional water management."),
]

CATEGORIES = [
    "Traditional Agriculture", "Seed Preservation", "Food Heritage", "Handicrafts",
    "Folk Culture", "Traditional Architecture", "Water & Environment", "Oral History",
    "Traditional Tools", "Local Plant Knowledge", "Ayurveda-related Traditional Knowledge",
    "Festivals & Traditions", "Vanishing Skills", "Local Products",
]

DEMO_USERS = [
    ("admin", "admin123", "admin", None),
    ("steward", "steward123", "steward", None),
    ("holder", "holder123", "user", "Bhotiya Weavers Collective"),
]

SAMPLE_RECORDS = [
    dict(
        district="Tehri Garhwal", category="Seed Preservation", community=None,
        access_level="public",
        title="Traditional seed storage using ash and clay pots",
        summary="Farmers in Tehri Garhwal traditionally store seeds for the next season in "
                "sun-dried clay pots layered with wood ash, which keeps out moisture and "
                "insects without any chemical treatment.",
        translation_en="In the old days, after the harvest, we would select the healthiest "
                        "grain, dry it fully in the sun for several days, then store it in "
                        "clay pots with a layer of wood ash mixed in. The ash kept the "
                        "insects away and the pot kept the moisture out. We sealed the pot "
                        "with a cloth and mud and kept it in a cool, dark corner of the house "
                        "until the next sowing season.",
        materials=["Wood ash", "Clay pots", "Cloth", "Mud for sealing"],
        tools=["Clay pot", "Winnowing tray"],
        steps=[
            "Select the healthiest, fullest grain after harvest",
            "Sun-dry the grain for several days until fully moisture-free",
            "Mix in a layer of wood ash through the grain",
            "Store in a clay pot, sealed with cloth and mud",
            "Keep in a cool, dark corner until the next sowing season",
        ],
        cultural_significance="This method is tied to household self-sufficiency and is "
                               "usually taught by mothers to daughters as part of running "
                               "the home.",
        historical_context="Predates chemical pesticide storage methods common in the plains.",
        keywords=["seed storage", "clay pot", "wood ash", "Tehri", "farming"],
        status="community_verified",
    ),
    dict(
        district="Pauri Garhwal", category="Vanishing Skills", community="Bhotiya Weavers Collective",
        access_level="community_only",
        title="Traditional wool weaving on a wooden loom",
        summary="A declining hand-weaving practice using undyed local sheep wool on a simple "
                "wooden loom, producing shawls and blankets for mountain winters.",
        translation_en="We shear the sheep in autumn, clean and card the wool by hand, spin "
                        "it into thread using a wooden spindle, then weave it on a simple "
                        "wooden loom set up at home. A single shawl can take two to three "
                        "weeks. Fewer young people are learning this now because the market "
                        "for hand-made wool has shrunk.",
        materials=["Raw sheep wool", "Natural dyes (optional)"],
        tools=["Wooden loom", "Hand spindle", "Wool carder"],
        steps=[
            "Shear sheep wool in autumn",
            "Clean and card the wool by hand",
            "Spin the wool into thread using a hand spindle",
            "Set up the wooden loom",
            "Weave the shawl or blanket, a process taking two to three weeks",
        ],
        cultural_significance="Wool garments are traditionally gifted at weddings and used "
                               "through the winter; the craft carries family identity in its "
                               "patterns.",
        historical_context="Documented informally for generations; formal documentation is "
                            "very limited today.",
        keywords=["wool weaving", "loom", "Pauri Garhwal", "textile", "vanishing craft"],
        status="community_verified",
    ),
    dict(
        district="Almora", category="Traditional Architecture", community=None,
        access_level="public",
        title="Slate-roofed stone house construction",
        summary="A traditional Kumaoni building method using dry stone walls and locally "
                "quarried slate roofing tiles, suited to heavy hill rainfall and snow.",
        translation_en="The walls are built from stones collected locally, fitted without "
                        "much cement in the old style, and the roof uses thin slate tiles "
                        "laid in overlapping rows so rain runs off easily. The slate also "
                        "keeps the house cool in summer and holds warmth in winter.",
        materials=["Local stone", "Slate tiles", "Wood beams", "Mud mortar"],
        tools=["Stone chisel", "Wooden mallet"],
        steps=[
            "Quarry and select flat local stones and slate",
            "Build dry stone walls with minimal mortar",
            "Place wooden beams for roof support",
            "Lay overlapping slate tiles for the roof",
        ],
        cultural_significance="Reflects Kumaoni village identity; many older homes are now "
                               "being replaced with concrete construction.",
        historical_context="Building method observed for multiple generations in the region.",
        keywords=["slate roof", "stone house", "Almora", "architecture"],
        status="community_verified",
    ),
    dict(
        district="Uttarkashi", category="Water & Environment", community=None,
        access_level="public",
        title="Naula spring-water management",
        summary="A traditional stepped-well system (naula) for collecting and protecting "
                "natural spring water, maintained collectively by the village.",
        translation_en="A naula is a small stone structure built around a natural spring, "
                        "with steps leading down to the water. The whole village takes turns "
                        "keeping it clean and clear of debris. It gives us drinking water "
                        "even in the dry months.",
        materials=["Local stone"],
        tools=["Stone chisel"],
        steps=[
            "Identify a natural spring source",
            "Build a stepped stone enclosure around it",
            "Maintain and clean the structure on a rotating village schedule",
        ],
        cultural_significance="Naulas are often considered sacred and are cared for as "
                               "shared community property.",
        historical_context="Common across the Central Himalayas for centuries.",
        keywords=["naula", "spring water", "Uttarkashi", "water management"],
        status="community_verified",
    ),
]

RISK_SEEDS = [
    dict(title="Traditional Wool Weaving", district="Pauri Garhwal", category="Vanishing Skills",
         practitioners=8, young_practitioners=1, documentation_level=1, frequency_trend=1,
         geographic_concentration=5, transmission_level=1,
         notes="Very few remaining weavers; almost no young learners; market has shrunk."),
    dict(title="Naula Spring-Water Maintenance", district="Uttarkashi", category="Water & Environment",
         practitioners=25, young_practitioners=10, documentation_level=3, frequency_trend=4,
         geographic_concentration=2, transmission_level=4,
         notes="Still actively maintained by several villages on a rotating basis."),
    dict(title="Slate Roof Construction", district="Almora", category="Traditional Architecture",
         practitioners=12, young_practitioners=2, documentation_level=2, frequency_trend=2,
         geographic_concentration=3, transmission_level=2,
         notes="Being replaced by concrete construction; few active builders remain."),
    dict(title="Clay Pot Seed Storage", district="Tehri Garhwal", category="Seed Preservation",
         practitioners=40, young_practitioners=15, documentation_level=3, frequency_trend=4,
         geographic_concentration=2, transmission_level=3,
         notes="Still common practice among older farming households."),
    dict(title="Wooden Water-Mill (Gharat) Operation", district="Chamoli", category="Traditional Tools",
         practitioners=5, young_practitioners=0, documentation_level=1, frequency_trend=1,
         geographic_concentration=4, transmission_level=1,
         notes="Nearly extinct; most gharats have been abandoned or converted."),
]


def run():
    app = create_app()
    with app.app_context():
        db = get_db()

        district_ids = {}
        for name, description in DISTRICTS:
            row = db.execute("SELECT id FROM districts WHERE name = ?", (name,)).fetchone()
            if row:
                district_ids[name] = row["id"]
                continue
            cur = db.execute(
                "INSERT INTO districts (name, slug, description) VALUES (?, ?, ?)",
                (name, slugify(name), description),
            )
            district_ids[name] = cur.lastrowid

        category_ids = {}
        for name in CATEGORIES:
            row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
            if row:
                category_ids[name] = row["id"]
                continue
            cur = db.execute(
                "INSERT INTO categories (name, slug) VALUES (?, ?)", (name, slugify(name))
            )
            category_ids[name] = cur.lastrowid

        db.commit()

        user_ids = {}
        for username, password, role, community in DEMO_USERS:
            row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row:
                user_ids[username] = row["id"]
                continue
            cur = db.execute(
                "INSERT INTO users (username, password_hash, role, community) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, community),
            )
            user_ids[username] = cur.lastrowid
        db.commit()

        existing_seed = db.execute(
            "SELECT COUNT(*) c FROM knowledge_records WHERE is_seed = 1"
        ).fetchone()["c"]
        if existing_seed == 0:
            for rec in SAMPLE_RECORDS:
                district_id = district_ids[rec["district"]]
                category_id = category_ids[rec["category"]]
                knowledge_id = next_knowledge_id(db, rec["district"], rec["category"])
                embedding = embed_text(
                    rec["summary"] + " " + rec["translation_en"] + " " + " ".join(rec["keywords"])
                )
                db.execute(
                    """INSERT INTO knowledge_records
                       (knowledge_id, title, district_id, category_id, community, language,
                        original_transcript, translation_en, materials, tools, steps,
                        cultural_significance, historical_context, summary, keywords,
                        status, access_level, contributor_id, embedding, is_seed)
                       VALUES (?, ?, ?, ?, ?, 'Hindi/Garhwali', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?, 1)""",
                    (
                        knowledge_id, rec["title"], district_id, category_id, rec["community"],
                        rec["translation_en"], rec["translation_en"],
                        json.dumps(rec["materials"]), json.dumps(rec["tools"]),
                        json.dumps(rec["steps"]), rec["cultural_significance"],
                        rec["historical_context"], rec["summary"], json.dumps(rec["keywords"]),
                        rec["status"], rec["access_level"], user_ids["holder"],
                        json.dumps(embedding),
                    ),
                )
            db.commit()
            print(f"Seeded {len(SAMPLE_RECORDS)} sample knowledge records.")
        else:
            print("Sample knowledge records already seeded, skipping.")

        existing_risk = db.execute("SELECT COUNT(*) c FROM risk_assessments").fetchone()["c"]
        if existing_risk == 0:
            for r in RISK_SEEDS:
                score, band, _ = compute_risk(
                    r["practitioners"], r["young_practitioners"], r["documentation_level"],
                    r["frequency_trend"], r["geographic_concentration"], r["transmission_level"],
                )
                db.execute(
                    """INSERT INTO risk_assessments
                       (practice_title, district_id, category_id, practitioners,
                        young_practitioners, documentation_level, frequency_trend,
                        geographic_concentration, transmission_level, score, band, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["title"], district_ids[r["district"]], category_ids[r["category"]],
                        r["practitioners"], r["young_practitioners"], r["documentation_level"],
                        r["frequency_trend"], r["geographic_concentration"], r["transmission_level"],
                        score, band, r["notes"],
                    ),
                )
            db.commit()
            print(f"Seeded {len(RISK_SEEDS)} risk assessments.")
        else:
            print("Risk assessments already seeded, skipping.")

        print("\nDemo accounts:")
        for username, password, role, _ in DEMO_USERS:
            print(f"  {username} / {password}  (role: {role})")


if __name__ == "__main__":
    run()
