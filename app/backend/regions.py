"""Where a player is from (user, 2026-11-28: "let someone pick their region, and put the region flag on their profile";
both a country and a game region). Chosen by the player with their bio (api/profiles.py), never worked out from data.

- COUNTRIES: ISO 3166 alpha-2 codes, lower case, plus England, Scotland, Wales and Northern Ireland; shown as the flag
  (the frontend's flag-icons pictures, the same codes: Windows does not draw flag emoji).
- REGIONS: the game's server regions, shown as text next to the flag.
"""

COUNTRIES = frozenset("""
    ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz
    ca cc cd cf cg ch ci ck cl cm cn co cp cr cu cv cw cx cy cz de dg dj dk dm do dz ec ee eg eh er es et fi fj fk
    fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu ic id ie il im in io iq ir
    is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml
    mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr
    ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj
    tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws xk ye yt za zm zw
""".split()) | {"gb-eng", "gb-sct", "gb-wls", "gb-nir"}

# key -> label; the order is the order of the picker
REGIONS = {
    "us-east": "US East",
    "us-central": "US Central",
    "us-west": "US West",
    "europe": "Europe",
    "japan": "Japan",
    "singapore": "Singapore",
    "australia": "Australia",
}


def clean_country(value: str | None) -> str | None:
    """A known country code (lower case) or None for none chosen; anything else raises ValueError."""
    if value is None or not value.strip():
        return None
    code = value.strip().lower()
    if code not in COUNTRIES:
        raise ValueError(code)
    return code


def clean_region(value: str | None) -> str | None:
    """A known region key or None for none chosen; anything else raises ValueError."""
    if value is None or not value.strip():
        return None
    key = value.strip().lower()
    if key not in REGIONS:
        raise ValueError(key)
    return key


# --- detected from the visitor's connection (user, 2026-11-28: "auto gather the region via their IP address too, unless
# it's manually set"). Cloudflare's CF-IPCountry header (no IP is kept or sent anywhere); the state / province comes
# only if Cloudflare's visitor location headers are on (cf-region-code), else US and Canada get the flag without a region.
EUROPE = frozenset("""
    ad al at ax ba be bg by ch cy cz de dk ee es fi fo fr gb gg gi gr hr hu ie im is it je li lt lu lv mc md me mk mt nl
    no pl pt ro rs ru se si sk sm ua va xk gb-eng gb-sct gb-wls gb-nir tr il
""".split())
JAPAN = frozenset({"jp", "kr", "tw", "hk", "mo"})
SINGAPORE = frozenset({"sg", "my", "id", "th", "vn", "ph", "kh", "la", "mm", "bn", "in"})
AUSTRALIA = frozenset({"au", "nz"})
US_WEST = frozenset({"WA", "OR", "CA", "NV", "ID", "UT", "AZ", "AK", "HI", "MT", "WY", "NM", "CO", "BC", "YT"})
US_CENTRAL = frozenset({"ND", "SD", "NE", "KS", "OK", "TX", "MN", "IA", "MO", "AR", "LA", "WI", "IL", "MS", "AL", "TN",
                        "AB", "SK", "MB", "NT", "NU"})


def region_for(country: str, state: str | None = None) -> str | None:
    """The game region nearest to a country (and US state / Canadian province, when known); None when unsure."""
    if country in EUROPE:
        return "europe"
    if country in JAPAN:
        return "japan"
    if country in SINGAPORE:
        return "singapore"
    if country in AUSTRALIA:
        return "australia"
    if country == "mx":
        return "us-central"
    if country in ("us", "ca") and state:
        code = state.strip().upper()
        return "us-west" if code in US_WEST else "us-central" if code in US_CENTRAL else "us-east"
    return None
