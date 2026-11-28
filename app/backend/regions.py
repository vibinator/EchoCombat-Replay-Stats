"""Where a player is from (user, 2026-11-28: "let someone pick their region, and put the region flag on their profile";
both a country and a game region). Chosen by the player with their bio (api/profiles.py), never worked out from data.

- COUNTRIES: ISO 3166 alpha-2 codes, lower case, plus England, Scotland, Wales and Northern Ireland; shown as the flag
  (the frontend's flag-icons pictures, the same codes: Windows does not draw flag emoji).
- REGIONS: the game's server regions, shown as text next to the flag. The region follows the country (REGION_OF);
  only US and Canadian players pick one (US East / Central / West).
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


# The game region follows the country (user, 2026-11-28: "the region should match the country"): one region per
# country, the nearest game servers; only the US and Canada span several, and their players pick one of the three.
_NEAREST = {
    "europe": """
        ad al at ax ba be bg by ch cy cz de dk ee es fi fo fr gb gg gi gr hr hu ie im is it je li lt lu lv mc md me mk mt
        nl no pl pt ro rs ru se si sj sk sm ua va xk ic bv tf gb-eng gb-sct gb-wls gb-nir
        tr il ae am az bh ge iq ir jo kw lb om ps qa sa sy ye kz kg tj tm uz
        dz ao bj bw bf bi cm cv cf td km cg cd ci dj eg gq er sz et ga gm gh gn gw ke ls lr ly mg mw ml mr mu yt ma mz
        na ne ng re rw sh st sn sc sl so za ss sd tz tg tn ug eh zm zw
    """,
    "japan": "jp kr kp tw hk mo cn mn",
    "singapore": "sg my id th vn ph kh la mm bn tl in pk bd lk np bt mv af io dg",
    "australia": "au nz fj pg sb vu nc pf ws to tv ki nr fm mh pw gu mp as ck nu tk wf pn nf cc cx hm aq",
    "us-east": """
        ar bo br cl co ec fk gf gy py pe sr uy ve gs gl pm
        ag ai aw bb bl bm bq bs cu cw dm do gd gp ht jm kn ky lc mf mq ms pr sx tc tt vc vg vi
    """,
    "us-central": "mx gt bz sv hn ni cr pa",
    "us-west": "um cp",
}
REGION_OF = {code: region for region, codes in _NEAREST.items() for code in codes.split()}
NORTH_AMERICA = ("us-east", "us-central", "us-west")
SEVERAL = {"us": NORTH_AMERICA, "ca": NORTH_AMERICA}  # the player (or their state / province) picks one


def regions_for(country: str | None) -> tuple[str, ...]:
    """The game regions that match a country: one, or three for the US and Canada; none without a country."""
    if not country:
        return ()
    return SEVERAL.get(country) or ((REGION_OF[country],) if country in REGION_OF else ())


def matching_region(country: str | None, region: str | None) -> str | None:
    """The region to keep with this country: the country's own one, or for the US and Canada the one given when it is
    one of theirs (else none yet). A region that does not match the country is never kept."""
    allowed = regions_for(country)
    if len(allowed) == 1:
        return allowed[0]
    return region if region in allowed else None


# --- detected from the visitor's connection (user, 2026-11-28: "auto gather the region via their IP address too, unless
# it's manually set"). Cloudflare's CF-IPCountry header (no IP is kept or sent anywhere); the state / province comes
# only if Cloudflare's visitor location headers are on (cf-region-code), else US and Canada get the flag without a region.
US_WEST = frozenset({"WA", "OR", "CA", "NV", "ID", "UT", "AZ", "AK", "HI", "MT", "WY", "NM", "CO", "BC", "YT"})
US_CENTRAL = frozenset({"ND", "SD", "NE", "KS", "OK", "TX", "MN", "IA", "MO", "AR", "LA", "WI", "IL", "MS", "AL", "TN",
                        "AB", "SK", "MB", "NT", "NU"})


def region_for(country: str, state: str | None = None) -> str | None:
    """The game region of a detected country (and US state / Canadian province, when known); None when not known."""
    if country in SEVERAL:
        if not state:
            return None
        code = state.strip().upper()
        return "us-west" if code in US_WEST else "us-central" if code in US_CENTRAL else "us-east"
    return matching_region(country, None)
