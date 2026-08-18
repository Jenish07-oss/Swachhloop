# brand.py — NagarLoop Branding, i18n Dictionary & Calculation Engine

BRAND = "NagarLoop"
SUB_BRAND = "Municipal Circular Waste Platform"
SLOGAN = {
    "en": "Your society's waste, back in the loop.",
    "gu": "તમારી સોસાયટીનો કચરો, ફરી લૂપમાં."
}
SUPPORT_EMAIL = "support@nagarloop.in"
CITY = "Ahmedabad"  # Configurable municipal jurisdiction

def format_pickup_code(pickup_id):
    """Generate standardized public-facing reference ID (e.g. NL-2026-00042)"""
    try:
        return f"NL-2026-{int(pickup_id):05d}"
    except (ValueError, TypeError):
        return f"NL-2026-{pickup_id}"

def calculate_green_points(stream_kg_dict, bin_score=80, is_society=False, is_public=False):
    """
    NagarLoop Proportional Green Points Engine (Phase 2 Spec)
    
    Rates:
      - Wet = 2 points/kg
      - Dry = 6 points/kg
      - E-Waste = 20 points/kg
      - Residual = 1 point/kg
      
    Bin Score Multipliers:
      - >= 80 -> 1.5
      - 60 - 79 -> 1.2
      - 40 - 59 -> 1.0
      - < 40 -> 0.5
      
    Special Rules:
      - Society booking below 5 kg total = 0 points
      - Public report = 15 points after verification (+5 if >10kg, +10 if >25kg)
    """
    total_kg = sum(float(kg) for kg in stream_kg_dict.values() if kg)
    
    if is_public:
        base_points = 15
        if total_kg >= 25.0:
            base_points += 10
        elif total_kg >= 10.0:
            base_points += 5
        return base_points

    if is_society and total_kg < 5.0:
        return 0

    wet_kg = float(stream_kg_dict.get('wet', 0.0) or 0.0)
    dry_kg = float(stream_kg_dict.get('dry', 0.0) or 0.0)
    ewaste_kg = float(stream_kg_dict.get('e_waste', 0.0) or stream_kg_dict.get('ewaste', 0.0) or 0.0)
    residual_kg = float(stream_kg_dict.get('residual', 0.0) or 0.0)

    raw_points = (wet_kg * 2.0) + (dry_kg * 6.0) + (ewaste_kg * 20.0) + (residual_kg * 1.0)

    if bin_score >= 80:
        multiplier = 1.5
    elif bin_score >= 60:
        multiplier = 1.2
    elif bin_score >= 40:
        multiplier = 1.0
    else:
        multiplier = 0.5

    return int(round(raw_points * multiplier))

def calculate_co2_impact(wet_kg=0.0, dry_kg=0.0, ewaste_kg=0.0, residual_kg=0.0):
    """
    Standardized Municipal Solid Waste GHG Offset Coefficients (ESTIMATE):
      - Wet (Bio-CNG / compost diversion from anaerobic landfill): 0.50 kg CO2e / kg
      - Dry (MRF recycling replacing virgin raw materials): 1.40 kg CO2e / kg
      - E-Waste (CPCB recovery of precious/toxic metals): 2.80 kg CO2e / kg
      - Residual (RDF co-processing in cement kiln offsetting coal): 0.30 kg CO2e / kg
    """
    wet = float(wet_kg or 0.0)
    dry = float(dry_kg or 0.0)
    ewaste = float(ewaste_kg or 0.0)
    residual = float(residual_kg or 0.0)
    co2 = (wet * 0.50) + (dry * 1.40) + (ewaste * 2.80) + (residual * 0.30)
    return round(co2, 1)

T = {
    "en": {
        "home": "Home",
        "book": "Book Pickup",
        "my_pickups": "My Pickups",
        "impact": "Impact",
        "board": "Leaderboard",
        "login": "Login",
        "register": "Register",
        "logout": "Logout",
        "help": "Help & Support",
        "privacy": "Privacy Policy",
        "rewards": "Green Rewards",
        "how": "How It Works",
        "separate": "1. Separate",
        "book_s": "2. Book",
        "collect": "3. Collect",
        "recover": "4. Recover",
        "join": "Join Your Society",
        "road": "Report Public Waste",
        "society": "Housing Societies",
        "home_user": "Individual Homes",
        "citizen": "Active Citizens",
        "start": "Get Started",
        "trusted": "Connecting societies, smart electric fleets & certified recyclers",
        # Booking section translations
        "book_title": "Book a 4-Stream Collection",
        "book_subtitle": "Select your segregated streams and estimated quantities. Smart electric vans ensure zero-mixing delivery to certified recycling facilities.",
        "start_booking": "Start Booking Below",
        "view_impact": "View My Impact",
        "your_balance": "Your Green Balance",
        "points_label": "Green Points",
        "society_code": "Society Code",
        "pickup_details": "Pickup Details",
        "segregate_subtitle": "Segregate at source to keep your city clean and earn Green Points.",
        "zero_mixing_guarantee": "Zero-Mixing Guarantee",
        "zero_mixing_mandate": "KEEP WASTE SEPARATE: Never mix the waste streams during collection.",
        "step1_title": "1. Select Segregated Streams & Estimated Quantity",
        "est_qty_note": "Estimated quantity (not exact weight)",
        "wet_name": "Wet / Organic Waste",
        "wet_desc": "Kitchen scraps, fruit peels & compostables.",
        "wet_dest": "GreenCycle Compost (2 pts/kg)",
        "dry_name": "Dry Recyclables",
        "dry_desc": "Paper, cardboard, plastics & metal cans.",
        "dry_dest": "Central MRF Baler (6 pts/kg)",
        "ewaste_name": "E-Waste",
        "ewaste_desc": "Batteries, old chargers, bulbs & electronics.",
        "ewaste_dest": "CPCB Recycler (20 pts/kg)",
        "residual_name": "Residual Non-Recyclable",
        "residual_desc": "Sanitary waste, sweepings & non-recyclables.",
        "residual_dest": "RDF Cement Kiln (1 pt/kg)",
        "step2_title": "2. Collection Location Pin",
        "step2_desc": "Doorstep collection within Navrangpura municipal ward.",
        "step3_title": "3. Attach Bin Photo (Optional)",
        "step3_desc": "Helps driver verify stream segregation and grants higher Bin Score.",
        "step4_title": "4. Confirm Doorstep Booking",
        "confirm_btn": "Confirm 4-Stream Collection",
        "summary_title": "Collection Summary",
        "selected_streams": "Selected Streams",
        "total_est_qty": "Total Estimated Weight",
        "est_points": "Estimated Green Points",
        "points_award_note": "Awarded upon successful driver collection & segregation score verification.",
        "repeat_pickup_banner": "Previous Pickup Details Pre-filled"
    },
    "gu": {
        "home": "મુખ્ય પાનું",
        "book": "કચરો બુક કરો",
        "my_pickups": "મારા પિકઅપ્સ",
        "impact": "અસર અને બચત",
        "board": "લીડરબોર્ડ",
        "login": "લૉગિન",
        "register": "નોંધણી",
        "logout": "લૉગઆઉટ",
        "help": "મદદ અને સપોર્ટ",
        "privacy": "ગોપનીયતા નીતિ",
        "rewards": "ગ્રીન ઇનામો",
        "how": "કેવી રીતે કામ કરે છે",
        "separate": "૧. વર્ગીકરણ",
        "book_s": "૨. બુક કરો",
        "collect": "૩. સંગ્રહ",
        "recover": "૪. પુનઃપ્રાપ્તિ",
        "join": "સોસાયટી સાથે જોડાઓ",
        "road": "જાહેર કચરાની જાણ કરો",
        "society": "હાઉસિંગ સોસાયટીઓ",
        "home_user": "સ્વતંત્ર મકાનો",
        "citizen": "જાગૃત નાગરિકો",
        "start": "શરૂ કરો",
        "trusted": "સોસાયટીઓ, સ્માર્ટ વાહનો અને રિસાયકલર્સ સાથે જોડાયેલ",
        # Booking section Gujarati translations
        "book_title": "૪-પ્રકાર કચરા સંગ્રહ બુક કરો",
        "book_subtitle": "તમારા વર્ગીકૃત કચરાના પ્રકાર અને અંદાજિત જથ્થો પસંદ કરો. સ્માર્ટ વાહનો ઝીરો-મિક્સિંગ ડિલિવરી સુનિશ્ચિત કરે છે.",
        "start_booking": "બુકિંગ શરૂ કરો",
        "view_impact": "મારી બચત જુઓ",
        "your_balance": "તમારું ગ્રીન બેલેન્સ",
        "points_label": "ગ્રીન પોઈન્ટ્સ",
        "society_code": "સોસાયટી કોડ",
        "pickup_details": "પિકઅપ વિગતો",
        "segregate_subtitle": "તમારા શહેરને સ્વચ્છ રાખવા અને ગ્રીન પોઈન્ટ્સ મેળવવા માટે કચરો અલગ રાખો.",
        "zero_mixing_guarantee": "ઝીરો-મિક્સિંગ ગેરંટી",
        "zero_mixing_mandate": "કચરો અલગ રાખો: સંગ્રહ દરમિયાન કચરાના પ્રવાહોને ક્યારેય મિશ્ર કરશો નહીં.",
        "step1_title": "૧. વર્ગીકૃત કચરાના પ્રકાર અને અંદાજિત જથ્થો પસંદ કરો",
        "est_qty_note": "અંદાજિત જથ્થો (ચોક્કસ વજન નથી)",
        "wet_name": "ભીનો / જૈવિક કચરો",
        "wet_desc": "રસોડાનો કચરો, ફળોની છાલ અને કમ્પોસ્ટેબલ વસ્તુઓ.",
        "wet_dest": "ગ્રીનસાયકલ કમ્પોસ્ટ (૨ પોઈન્ટ્સ/કિગ્રા)",
        "dry_name": "સૂકો રિસાયકલ કચરો",
        "dry_desc": "કાગળ, કાર્ડબોર્ડ, પ્લાસ્ટિક અને ધાતુના ડબ્બા.",
        "dry_dest": "સેન્ટ્રલ MRF બેલર (૬ પોઈન્ટ્સ/કિગ્રા)",
        "ewaste_name": "ઈ-વેસ્ટ (ઇલેક્ટ્રોનિક્સ)",
        "ewaste_desc": "બેટરી, જૂના ચાર્જર, બલ્બ અને ઇલેક્ટ્રોનિક્સ.",
        "ewaste_dest": "CPCB રજિસ્ટર્ડ રિસાયકલર (૨૦ પોઈન્ટ્સ/કિગ્રા)",
        "residual_name": "અન્ય બિન-રિસાયકલ કચરો",
        "residual_desc": "સેનિટરી કચરો, ધૂળ-કચરો અને મિશ્ર બિન-રિસાયકલ કચરો.",
        "residual_dest": "RDF સિમેન્ટ ભઠ્ઠી (૧ પોઈન્ટ/કિગ્રા)",
        "step2_title": "૨. સંગ્રહ સ્થાન પિન ચકાસો",
        "step2_desc": "નવરંગપુરા મ્યુનિસિપલ વોર્ડમાં ઘરબેઠા સંગ્રહ.",
        "step3_title": "૩. ડબ્બાનો ફોટો જોડો (વૈકલ્પિક)",
        "step3_desc": "ડ્રાઈવરને વર્ગીકરણ ચકાસવામાં મદદ કરે છે અને વધુ પોઈન્ટ્સ અપાવે છે.",
        "step4_title": "૪. ઘરબેઠા સંગ્રહ કન્ફર્મ કરો",
        "confirm_btn": "૪-પ્રકાર કચરા સંગ્રહ કન્ફર્મ કરો",
        "summary_title": "સંગ્રહ સારાંશ",
        "selected_streams": "પસંદ કરેલ પ્રવાહો",
        "total_est_qty": "કુલ અંદાજિત વજન",
        "est_points": "અંદાજિત ગ્રીન પોઈન્ટ્સ",
        "points_award_note": "ડ્રાઈવર દ્વારા સફળ સંગ્રહ અને વર્ગીકરણ સ્કોર ચકાસણી પછી જમા થશે.",
        "repeat_pickup_banner": "અગાઉના પિકઅપની વિગતો આપમેળે ભરેલી છે"
    }
}
