"""
generate_assets.py — Star Raise Game Art Generator
====================================================
使用 Gemini API 批次生成 39 張遊戲美術圖：
  • 21 種建築 (Federation × 7 / Swarm × 7 / Rogue AI × 7)
  • 18 種單位  (Federation × 6 / Swarm × 6 / Rogue AI × 6)

使用方式：
  pip install google-genai pillow
  python generate_assets.py

注意：執行前請設定 GEMINI_API_KEY 環境變數，或在下方直接填入。
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

# ── 依賴檢查 ──────────────────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types
except ImportError:
    sys.exit("❌ 缺少套件，請先執行：pip install google-genai")

try:
    from PIL import Image
except ImportError:
    sys.exit("❌ 缺少套件，請先執行：pip install pillow")


# ══════════════════════════════════════════════════════════════════════════════
#  設定區 — 請在此填入 API Key 或設定環境變數 GEMINI_API_KEY
# ══════════════════════════════════════════════════════════════════════════════
API_KEY: str = os.environ.get("GEMINI_API_KEY", "")   # ← 或直接在此填 Key

if not API_KEY:
    API_KEY = input("請輸入 Gemini API Key：").strip()

# ── 候選模型（依序嘗試，第一個成功的就用它）──────────────────────────────────
CANDIDATE_MODELS: list[str] = [
    "gemini-3.1-flash-image-preview",   # 主要：最新 flash 圖片生成模型
    "gemini-3-pro-image-preview",       # 備用：pro 級圖片品質更佳
    "gemini-2.5-flash-image",           # 再備用：2.5 flash image
]

# v1beta 與 v1alpha 都支援這些 preview 模型
API_VERSION = "v1beta"

OUTPUT_DIR    = Path("assets/generated")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RETRY_LIMIT   = 3      # 每張圖最多重試次數
RETRY_DELAY   = 10.0   # 重試等待秒數
REQUEST_DELAY = 4.0    # 每次請求之間的間隔（避免速率限制）


# ══════════════════════════════════════════════════════════════════════════════
#  全域風格說明 (所有資產共用)
# ══════════════════════════════════════════════════════════════════════════════
GLOBAL_STYLE = (
    "Professional RTS game sprite art in the style of StarCraft II / Warcraft III. "
    "2.5D isometric perspective at exactly 60-degree viewing angle from above-front. "
    "Strong, readable silhouette that remains clear when scaled down to 64×64 pixels. "
    "Dramatic rim lighting from upper-left with vibrant saturated colors. "
    "Clean transparent PNG background — no ground shadow, no floor tiles, no platform base beneath the subject. "
    "Single centered subject filling 80% of the canvas. "
    "High-detail textures with crisp outlines. "
    "Consistent painterly-pixel hybrid art style across all assets. "
    "No HUD, no text, no UI elements, no watermarks."
)

# 種族視覺語言
FED_STYLE = (
    "Federation faction aesthetics: military sci-fi, angular steel-gray armor plating, "
    "cobalt-blue energy accents and lighting, gold trim details, "
    "mechanical rivets and hydraulics visible, human engineering precision, "
    "NO organic or biological elements whatsoever."
)

SWARM_STYLE = (
    "Swarm faction aesthetics: alien insectoid bio-organism, "
    "deep purple chitinous exoskeleton with acid-green bioluminescent veins, "
    "wet glistening organic surfaces, mandibles and spines, "
    "NO metallic parts, NO mechanical technology, NO human engineering elements. "
    "Purely biological creature or structure."
)

ROGUE_STYLE = (
    "Rogue AI faction aesthetics: corrupted autonomous machine, "
    "matte obsidian black chassis with glowing electric-cyan circuit patterns, "
    "warning-orange plasma energy cores, angular geometric forms, "
    "glitching corrupted surfaces with exposed wiring, "
    "NO organic or biological elements whatsoever."
)

# 單位額外規則
UNIT_RULES = (
    "CRITICAL RULES FOR UNIT SPRITES: "
    "(1) The unit MUST face toward the RIGHT side of the image — this is mandatory. "
    "(2) The FULL body of the unit must be visible — absolutely NO cropping of legs, feet, or lower body. "
    "(3) DO NOT place any base, pedestal, platform, or ground tile beneath the unit. "
    "(4) The unit stands or hovers freely in empty space with transparent background."
)

# 建築額外規則
BUILDING_RULES = (
    "CRITICAL RULES FOR BUILDING SPRITES: "
    "(1) Show the building from 2.5D isometric 60-degree angle. "
    "(2) The full structure must be visible — no cropping. "
    "(3) NO units, soldiers, or creatures around or inside the building. "
    "(4) NO ground tiles or terrain — the building sits on transparent background."
)


# ══════════════════════════════════════════════════════════════════════════════
#  資產定義表
#  格式：(output_filename, category, faction_style, unique_description)
# ══════════════════════════════════════════════════════════════════════════════

ASSETS: list[tuple[str, str, str, str]] = [

    # ──────────────────────────────────────────────────────────────────────────
    # FEDERATION — 建築 (7)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "hq",
        "building",
        FED_STYLE,
        "Federation Headquarters fortress: a massive three-tiered military command citadel. "
        "Thick reinforced steel walls with angular battlements. Giant holographic blue globe "
        "display on top. Multiple gun turret emplacements on corners. Federation eagle emblem "
        "engraved on the front gate. Blue energy shield generators on the sides. "
        "Imposing and dominant — clearly the most powerful structure on the battlefield. "
        "Size: very large, occupies full canvas height."
    ),
    (
        "barracks",
        "building",
        FED_STYLE,
        "Federation Barracks infantry training facility: a military-grade two-story building "
        "with steel blast doors at front. Blue 'BARRACKS' holographic sign above entrance. "
        "Firing range targets visible on the side wall. Ventilation fans on the roof. "
        "Military antenna array on top. Compact and utilitarian design. "
        "Warm interior light leaking from the blast door gap."
    ),
    (
        "rover_bay",
        "building",
        FED_STYLE,
        "Federation Rover Bay vehicle garage: a wide hangar building with large reinforced "
        "sliding metal doors, open slightly to reveal blue light inside. "
        "Vehicle tire tracks on the approach ramp. Mechanical crane arm extending from the roof. "
        "Fuel tanks on the side. Diagnostic screens on the outer wall. "
        "Industrial and functional aesthetic with exposed metal framework."
    ),
    (
        "spec_ops",
        "building",
        FED_STYLE,
        "Federation Spec Ops Center: a sleek low-profile intelligence facility. "
        "Dark tinted windows with blue glow, signal-jamming dishes on the roof. "
        "Encrypted data terminals visible through a small window. "
        "Heavy security keypad locks on reinforced doors. Cloaking field emitter on top. "
        "Classified-looking with stealth paneling — more angular and secretive than other buildings."
    ),
    (
        "refinery",
        "building",
        FED_STYLE,
        "Federation Refinery armored vehicle factory: a large industrial plant with "
        "a central assembly line visible through open panels. Mechanical robotic arms "
        "extending from the structure. Exhaust stacks releasing blue plasma steam. "
        "Heavy press machinery visible inside. Mineral ore conveyor belt on the side. "
        "Functional, heavy-industry aesthetic with yellow caution stripes."
    ),
    (
        "heavy_factory",
        "building",
        FED_STYLE,
        "Federation Heavy Factory weapons manufacturing plant: an enormous fortress-like factory. "
        "Huge blast doors reinforced with multiple hydraulic locks. "
        "Giant missile silos visible at the back. Overhead gantry crane. "
        "Thick armor plating on all walls. Warning lights flashing orange. "
        "The largest non-HQ Federation building — massive and imposing industrial scale."
    ),
    (
        "starport",
        "building",
        FED_STYLE,
        "Federation Starport aircraft launch facility: a wide, low-profile aerospace hangar "
        "with an open launch pad on top. Blue landing guide lights along the runway edges. "
        "Radar dish rotating on one corner. Jet fuel tanks on the sides. "
        "Launch catapult rail system visible on the roof pad. "
        "Air traffic control tower with glowing blue windows."
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # SWARM — 建築 (7)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "swarm_hq",
        "building",
        SWARM_STYLE,
        "Swarm Hive Core headquarters: a colossal pulsating bio-mass structure. "
        "Central throbbing queen-chamber with glowing purple heart visible through translucent chitin walls. "
        "Massive organic tendrils sprawling outward. Acid-green bioluminescent pustules "
        "covering the surface. Spore vents releasing green mist. "
        "Overwhelming organic presence — clearly the apex Swarm structure. "
        "Living, breathing, grotesque beauty."
    ),
    (
        "acid_pool",
        "building",
        SWARM_STYLE,
        "Swarm Acid Pool breeding chamber: a wide organic bowl-shaped structure filled with "
        "bubbling bright acid-green liquid. Larval eggs floating in the acid. "
        "Chitinous rim with fleshy organic veins feeding into the pool. "
        "Small crawler larvae emerging from the liquid. "
        "Acid vapor rising as glowing green mist. Grotesque but vibrant."
    ),
    (
        "toxin_chamber",
        "building",
        SWARM_STYLE,
        "Swarm Toxin Chamber spore production organ: a tall bulbous organic sac "
        "with multiple nozzle-like spore ejection tubes pointing upward. "
        "Pulsating purple and green veins running across the surface. "
        "Toxic spores visibly erupting from the tubes. "
        "Gelatinous membrane stretched over the main chamber. "
        "Smaller satellite sacs attached by organic tubes."
    ),
    (
        "mutation_pit",
        "building",
        SWARM_STYLE,
        "Swarm Mutation Pit evolution vat: a deep circular organic pit structure "
        "with a massive throbbing bio-membrane stretched over the opening. "
        "Grotesque mutating forms visible through the translucent membrane. "
        "DNA helix-like organic spirals growing from the sides. "
        "Bright purple mutation energy glowing from within. "
        "The structure looks alive and constantly morphing."
    ),
    (
        "hive_nest",
        "building",
        SWARM_STYLE,
        "Swarm Hive Nest flying creature nursery: a tall layered organic tower "
        "resembling a giant wasp nest, made of hardened chitinous resin. "
        "Multiple hexagonal cell openings with green glow inside. "
        "Organic buttresses supporting the structure. "
        "Empty cocoons hanging from the sides. "
        "Flying creature wing membranes visible at the nest openings."
    ),
    (
        "spine_ridge",
        "building",
        SWARM_STYLE,
        "Swarm Spine Ridge defensive structure: a cluster of enormous bone-white "
        "chitinous spines erupting from a central organic mound. "
        "The spines are razor-sharp and angled forward menacingly. "
        "Bioluminescent green fluid running through the base veins. "
        "Smaller defensive quills surrounding the main spines. "
        "Visually like a living cactus made of alien bone-spikes."
    ),
    (
        "scourge_nest",
        "building",
        SWARM_STYLE,
        "Swarm Scourge Nest explosive creature hive: a dense organic cluster "
        "of round pulsating bio-sacs, each glowing with volatile orange-green energy. "
        "Multiple tunnel openings in the organic mass for creatures to emerge. "
        "Unstable bio-chemical residue dripping from the sacs. "
        "The structure looks volatile and dangerous — ready to burst at any moment."
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # ROGUE AI — 建築 (7)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "rogue_hq",
        "building",
        ROGUE_STYLE,
        "Rogue AI Core Mainframe headquarters: a towering monolithic black server-fortress. "
        "Central massive glowing cyan data core at the center, visible through glass panels. "
        "Thousands of circuit trace lines illuminated in electric blue running up the walls. "
        "Holographic data streams flowing around the structure. "
        "Corrupted orange error warnings flickering on some panels. "
        "The most imposing and alien-looking structure on the battlefield. "
        "Feels like an ancient evil computer god awakening."
    ),
    (
        "sensor_array",
        "building",
        ROGUE_STYLE,
        "Rogue AI Sensor Array detection station: a geometric cluster of angular "
        "satellite dishes and sensor antennae, all pointed in different directions. "
        "Each dish has a glowing cyan scanning beam emanating from it. "
        "Central processing hub connecting all dishes with circuit tubes. "
        "Data readout screens covering the base structure. "
        "Sleek black finish with minimal but precise design."
    ),
    (
        "data_node",
        "building",
        ROGUE_STYLE,
        "Rogue AI Data Node processing unit: a tall elegant black obelisk-shaped "
        "structure with cascading cyan digital code flowing down its faces. "
        "Multiple data transfer cables connecting to the ground. "
        "Central glowing orange quantum processor visible inside the glass core. "
        "Compact but radiating immense computational power. "
        "Geometric precision with clean angular surfaces."
    ),
    (
        "assembly_matrix",
        "building",
        ROGUE_STYLE,
        "Rogue AI Assembly Matrix manufacturing complex: a wide flat factory platform "
        "with robotic assembly arms in constant motion, arranged in a precise grid pattern. "
        "Blueprint hologram projecting above the structure. "
        "Half-assembled mechanical units visible on the production rails. "
        "Electric sparks from the welding arms. "
        "Highly organized and efficient — a machine making machines."
    ),
    (
        "plasma_forge",
        "building",
        ROGUE_STYLE,
        "Rogue AI Plasma Forge weapons foundry: a fortified black geometric structure "
        "with a central plasma containment column, glowing intense orange-white. "
        "Magnetic containment rings surrounding the plasma column. "
        "Superheated orange plasma energy venting from release valves. "
        "Heavy reinforced walls with heat-dissipation fins. "
        "Visually hot and dangerous — the forge of destruction."
    ),
    (
        "quantum_core",
        "building",
        ROGUE_STYLE,
        "Rogue AI Quantum Core energy powerplant: a striking crystalline black structure "
        "surrounding a central floating quantum crystal, radiating brilliant cyan light. "
        "Reality-distortion effects visible around the crystal — space slightly warped. "
        "Energy conduits drawing power from the crystal to surrounding pylons. "
        "The crystal rotates slowly, defying gravity. "
        "The most visually spectacular Rogue AI building."
    ),
    (
        "oblivion_engine",
        "building",
        ROGUE_STYLE,
        "Rogue AI Oblivion Engine annihilation device: an enormous terrifying "
        "weapons platform — a massive black fortress-machine with a central "
        "charged particle cannon barrel pointing forward. "
        "Orange-red annihilation energy charging in the barrel chamber. "
        "Multiple reinforcing struts holding the cannon in place. "
        "Warning lights and error codes flickering across the surface. "
        "The most intimidating structure in the game — a weapon of mass destruction. "
        "Size: very large."
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # FEDERATION — 單位 (6)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "marine",
        "unit",
        FED_STYLE,
        "Federation Marine infantry soldier: a medium-height soldier in full cobalt-blue "
        "powered combat armor with white trim. Helmet with a blue visor. "
        "Holding a pulse rifle aimed forward (to the right). "
        "Strong, confident military stance — slightly crouched, battle-ready. "
        "Shoulder pauldrons with Federation eagle insignia. "
        "Boot-clad feet clearly visible at the bottom of the frame."
    ),
    (
        "jackal",
        "unit",
        FED_STYLE,
        "Federation Jackal assault buggy vehicle: a fast angular two-wheeled (or four-wheeled) "
        "military scout vehicle with a mounted rotary gun on top, pointing right. "
        "Sleek aerodynamic chassis in steel gray with blue stripe. "
        "Large off-road tires. Driver visible in open cockpit. "
        "Vehicle facing fully to the right. "
        "All four wheels visible and on the same level — no ground surface beneath. "
        "Entire vehicle from bumper to bumper fits within the frame."
    ),
    (
        "ghost",
        "unit",
        FED_STYLE,
        "Federation Ghost stealth operative: a tall slender figure in form-fitting "
        "dark navy stealth suit with integrated cloaking panels. "
        "Advanced sniper rifle with holographic scope, aimed to the right. "
        "Glowing blue visor on sleek helmet. Tactical pouches on belt. "
        "Elegant but deadly posture, slightly crouched facing right. "
        "Full figure from head to toes visible in frame."
    ),
    (
        "tank",
        "unit",
        FED_STYLE,
        "Federation Tank heavy siege vehicle: a wide powerful military tank "
        "with a large main cannon barrel pointing to the right. "
        "Heavy composite armor plating. Federation markings on the hull. "
        "Caterpillar tracks on both sides. "
        "Tank seen from 2.5D isometric angle, facing right. "
        "Full vehicle from cannon tip to rear visible — no cropping. "
        "No ground surface, floating on transparent background."
    ),
    (
        "hellfire",
        "unit",
        FED_STYLE,
        "Federation Hellfire rocket artillery: a heavy military vehicle with "
        "a massive multi-tube rocket launcher battery on top, elevated and pointing right. "
        "Stabilizer legs deployed at the sides. "
        "Smoke trails visible from recently fired rockets. "
        "Bulky reinforced chassis in olive-gray with blue accents. "
        "Full vehicle visible from front to back. No ground under it."
    ),
    (
        "valkyrie",
        "unit",
        FED_STYLE,
        "Federation Valkyrie assault gunship: a futuristic attack helicopter/VTOL aircraft "
        "flying and facing to the right. "
        "Sleek aerodynamic fuselage in cobalt blue and white. "
        "Twin rotors or jet VTOL engines visible. "
        "Wing-mounted missile pods. Cockpit with glowing blue glass. "
        "Flying freely in empty space — no ground, no landing struts deployed. "
        "Full aircraft from nose to tail clearly visible."
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # SWARM — 單位 (6)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "crawler",
        "unit",
        SWARM_STYLE,
        "Swarm Crawler fast insect ground unit: a small but ferocious six-legged "
        "insectoid creature with large slashing claws, facing to the right. "
        "Compact armored purple chitin carapace. "
        "Multiple sharp legs spread low to the ground. "
        "Aggressive forward-lunging posture, all legs visible. "
        "Glowing green eyes. Small but clearly menacing. "
        "Full body from head to all leg-tips visible — nothing cropped."
    ),
    (
        "spitter",
        "unit",
        SWARM_STYLE,
        "Swarm Spitter acid-ranged alien: a mid-sized bipedal insectoid creature "
        "with an elongated neck and large organic acid-sac on its back, facing right. "
        "Mouth open with bright green acid glob being projected to the right. "
        "Four limbs — two grasping arms, two thick hind legs planted firmly. "
        "Acid-green pustules on purple chitinous body. "
        "Full body from head to feet visible — no cropping at bottom."
    ),
    (
        "crusher",
        "unit",
        SWARM_STYLE,
        "Swarm Crusher massive siege beast: a huge heavily-armored alien creature "
        "resembling an armored beetle or rhinoceros beetle, facing to the right. "
        "Enormous reinforced chitinous shell on its back. "
        "Two giant crushing claws at the front. "
        "Six thick powerful legs visible beneath the massive body. "
        "Slow but unstoppable look — immense weight implied. "
        "Full creature from horn tips to all feet visible."
    ),
    (
        "weaver",
        "unit",
        SWARM_STYLE,
        "Swarm Weaver flying mantis: an elegant but terrifying flying alien predator "
        "resembling a praying mantis with large membranous wings spread wide, facing right. "
        "Two massive scything blade-arms at the front. "
        "Hovering freely in the air — wings fully extended. "
        "Slender body with iridescent purple and green coloring. "
        "Compound eyes glowing green. Long segmented tail. "
        "Full creature from wing-tip to wing-tip and head to tail visible."
    ),
    (
        "impaler",
        "unit",
        SWARM_STYLE,
        "Swarm Impaler spike creature: a large aggressive alien organism facing right, "
        "with multiple massive bone-white spines erupting from its back and shoulders. "
        "Powerful quadruped stance with heavy armored forearms. "
        "Launching or rearing back to stab forward with a giant spike-limb. "
        "Chitinous purple armor with bioluminescent green cracks. "
        "All four limbs and the spines clearly visible — no cropping."
    ),
    (
        "scourge",
        "unit",
        SWARM_STYLE,
        "Swarm Scourge explosive suicide flyer: a small round flying alien organism "
        "like a bloated volatile bomb-creature with small wings, facing right. "
        "Body filled with volatile acid-green explosive bio-fluid glowing from within. "
        "Wide open maw ready to bite. Erratic wing membranes. "
        "Unstable, volatile look — clearly a living bomb. "
        "Small but dangerous. Full body visible — no cropping."
    ),

    # ──────────────────────────────────────────────────────────────────────────
    # ROGUE AI — 單位 (6)
    # ──────────────────────────────────────────────────────────────────────────
    (
        "observer",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Observer flying drone: a small spherical reconnaissance drone "
        "hovering in the air, facing to the right. "
        "Sleek matte black shell with a single large glowing cyan sensor eye. "
        "Multiple thin antenna probes extending from the sphere. "
        "Small repulsor field rings beneath it (not a platform — just energy rings). "
        "Compact and precise. Full sphere and all antennae visible."
    ),
    (
        "coder",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Coder digital warfare unit: a hovering abstract entity "
        "resembling a floating geometric wireframe humanoid made of pure digital code, "
        "facing to the right. "
        "Body composed of cascading cyan data streams and glowing orange circuit nodes. "
        "Arms extended forward firing a piercing data-beam to the right. "
        "Translucent, ethereal yet clearly mechanical. "
        "Full figure from top to bottom visible — hovering above transparent background."
    ),
    (
        "sentinel",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Sentinel heavy guardian robot: a tall imposing bipedal combat robot "
        "facing to the right. "
        "Massive reinforced black chassis with cyan energy lines across the chest plate. "
        "Heavy shoulder-mounted beam cannon aimed to the right. "
        "Thick armored legs with hydraulic joint details. "
        "Single large triangular orange targeting sensor on the face. "
        "Battle-damaged surface with exposed wiring. "
        "Full robot from head to feet visible."
    ),
    (
        "obliterator",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Obliterator super-heavy death machine: an enormous terrifying "
        "quadruped war machine facing right. "
        "Huge black armored body with a massive siege cannon barrel on top, pointing right. "
        "Four giant mechanical legs — each as thick as a tree trunk. "
        "Orange plasma energy charging in the cannon breach. "
        "Battle-scarred surface — the most feared unit on the battlefield. "
        "All four legs and full body from cannon to rear clearly visible."
    ),
    (
        "tracker",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Tracker fast spider robot: a sleek six-legged spider-like surveillance "
        "robot facing to the right. "
        "Low-profile aerodynamic black body with cyan laser emitters on the front. "
        "Long precise mechanical legs allowing swift movement. "
        "Multiple sensor eyes glowing orange on the front-facing head. "
        "Agile and precise. Full body from front legs to rear legs visible."
    ),
    (
        "purifier",
        "unit",
        ROGUE_STYLE,
        "Rogue AI Purifier heavy laser platform: a large hovering flying weapons platform "
        "facing to the right. "
        "Wide flat hexagonal body in matte black with three large laser cannon emitters "
        "pointing to the right. "
        "Repulsor anti-gravity rings beneath the platform (energy rings, not a solid base). "
        "Intense cyan laser beams charging at the cannon tips. "
        "Ominous and powerful. Full platform from front cannons to rear thrusters visible."
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
#  生成引擎
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(category: str, faction_style: str, unique_desc: str) -> str:
    """組合最終送出的完整 Prompt。"""
    rules = UNIT_RULES if category == "unit" else BUILDING_RULES
    return (
        f"{GLOBAL_STYLE}\n\n"
        f"FACTION VISUAL IDENTITY: {faction_style}\n\n"
        f"SUBJECT DESCRIPTION: {unique_desc}\n\n"
        f"{rules}"
    )


def save_image(data: bytes, mime_type: str, path: Path) -> None:
    """將 API 返回的圖片 bytes 存成 PNG。"""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img.save(path.with_suffix(".png"), "PNG")


def _make_client(api_version: str = "v1alpha") -> genai.Client:
    """建立指定 API 版本的 Gemini client。"""
    return genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(api_version=api_version),
    )


def detect_image_model(client: genai.Client) -> str:
    """
    掃描帳號可用的模型，找出支援圖片輸出的那一個。
    優先使用 CANDIDATE_MODELS 清單中的順序。
    若都找不到就回傳清單第一個（讓後續失敗時給出清楚錯誤）。
    """
    print("  🔍 掃描可用的圖片生成模型…")
    try:
        available = {m.name.split("/")[-1] for m in client.models.list()}
        print(f"     找到 {len(available)} 個模型")
        for candidate in CANDIDATE_MODELS:
            short = candidate.split("/")[-1]
            if short in available or candidate in available:
                print(f"     ✅ 使用模型：{candidate}")
                return candidate
        # 如果候選名稱都不在清單裡，印出部分可用名稱供參考
        image_hints = [n for n in available if "image" in n or "flash" in n or "imagen" in n]
        if image_hints:
            print(f"     ⚠  候選模型未找到，可用的相關模型：{image_hints[:8]}")
            print(f"        請在腳本頂部的 CANDIDATE_MODELS 清單中加入正確名稱後重跑。")
    except Exception as e:
        print(f"     ⚠  無法列出模型（{e}），直接嘗試候選清單。")

    return CANDIDATE_MODELS[0]


def generate_one(
    client: genai.Client,
    model: str,
    asset_name: str,
    category: str,
    faction_style: str,
    unique_desc: str,
) -> bool:
    """
    為單一資產呼叫 Gemini API，成功則存檔並回傳 True。
    失敗 RETRY_LIMIT 次後回傳 False。
    """
    out_path = OUTPUT_DIR / f"{asset_name}.png"

    if out_path.exists():
        print(f"  ⏭  {asset_name}.png 已存在，略過")
        return True

    prompt = build_prompt(category, faction_style, unique_desc)

    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            # 從回應中找圖片 part
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    save_image(part.inline_data.data, part.inline_data.mime_type, out_path)
                    print(f"  ✅  {asset_name}.png 已儲存")
                    return True

            # 沒有圖片 part → 印出文字回應供除錯
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    print(f"     ⚠  API 文字回應：{part.text[:200]}")
            print(f"  ⚠  {asset_name}: 回應中無圖片 (attempt {attempt}/{RETRY_LIMIT})")

        except Exception as exc:
            err_str = str(exc)
            print(f"  ❌  {asset_name} 第 {attempt} 次失敗：{err_str[:200]}")
            # 若是模型不存在的 404，不必重試
            if "NOT_FOUND" in err_str or "404" in err_str:
                print(f"     ℹ  模型 '{model}' 不可用，請檢查 CANDIDATE_MODELS 設定。")
                return False
            if attempt < RETRY_LIMIT:
                print(f"     ⏳  等待 {RETRY_DELAY}s 後重試…")
                time.sleep(RETRY_DELAY)

    print(f"  💀  {asset_name} 在 {RETRY_LIMIT} 次嘗試後放棄")
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  主程式
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("\n" + "═" * 60)
    print("  Star Raise — Gemini 美術資產生成器")
    print(f"  共 {len(ASSETS)} 個資產  →  輸出至 {OUTPUT_DIR.resolve()}")
    print("═" * 60 + "\n")

    # 使用 v1alpha 支援 preview 模型
    client = _make_client(API_VERSION)

    # 自動偵測可用的圖片生成模型
    model = detect_image_model(client)

    success_count = 0
    fail_list: list[str] = []

    # 分類顯示進度
    factions = {
        "FEDERATION 聯邦軍": [a for a in ASSETS if a[2] is FED_STYLE],
        "SWARM 蟲群":        [a for a in ASSETS if a[2] is SWARM_STYLE],
        "ROGUE AI 叛亂AI":   [a for a in ASSETS if a[2] is ROGUE_STYLE],
    }

    total_done = 0
    for faction_name, faction_assets in factions.items():
        print(f"\n{'─' * 50}")
        print(f"  ▶  {faction_name}  ({len(faction_assets)} 個)")
        print(f"{'─' * 50}")

        for name, category, faction_style, desc in faction_assets:
            total_done += 1
            label = f"[{total_done:02d}/{len(ASSETS)}] [{category.upper()}]"
            print(f"\n{label} 生成: {name}")

            ok = generate_one(client, model, name, category, faction_style, desc)
            if ok:
                success_count += 1
            else:
                fail_list.append(name)
                # 若是模型根本不存在，直接中止，不必跑完 39 個
                if success_count == 0 and len(fail_list) == 1:
                    print("\n  ⛔ 第一個資產就失敗，可能是模型名稱問題，中止執行。")
                    print("     請執行下方的 list_models.py 確認正確模型名稱。")
                    _print_summary(success_count, fail_list)
                    return

            if total_done < len(ASSETS):
                time.sleep(REQUEST_DELAY)

    _print_summary(success_count, fail_list)


def _print_summary(success_count: int, fail_list: list[str]) -> None:
    print("\n" + "═" * 60)
    print(f"  完成！成功: {success_count} / {len(ASSETS)}")
    if fail_list:
        print(f"  失敗清單: {', '.join(fail_list)}")
        print(f"  提示：可重新執行腳本，已成功的檔案將自動略過。")
    print(f"  圖片位置: {OUTPUT_DIR.resolve()}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
