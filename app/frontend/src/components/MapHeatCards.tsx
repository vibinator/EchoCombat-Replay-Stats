import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { getMapHeat, type MapHeat, type MapHeatLayer, type MapHeatView } from "../api";
import { minimapUrl, pct, title } from "../format";
import { useApi } from "../useApi";
import { GearLabel } from "./common";
import { decodeEntries, entryAt, readOut, type Entries } from "./heatRead";

const HEAT_GROUPS: [MapHeatLayer["group"], string][] = [
  ["team", "Teams"],
  ["weapon", "Weapon"],
  ["ordnance", "Ordnance"],
  ["tacmod", "Tac mod"],
  ["hand", "Handed"],
  ["pose", "Upside down"],
  ["speed", "Speed"],
  ["death", "Deaths"],
  ["payload", "Payload"],
];
/** Layers that can be compared with, besides the ones the answer lists: the two teams on their own. */
const HEAT_TEAMS: [string, string][] = [
  ["team:blue", "Blue team"],
  ["team:orange", "Orange team"],
];

const HEAT_VIEWS: [MapHeatView, string, string][] = [
  ["favoured", "Favoured spots", "Where it is more often than on the map as a whole"],
  ["all", "Everywhere", "Everywhere it was"],
];

/** Time ranges (map_heat.RANGES): days back from today, 0 = all time. */
const HEAT_RANGES: [number, string, string][] = [
  [0, "All time", "all time"],
  [90, "Last 90 days", "the last 90 days"],
  [30, "Last 30 days", "the last 30 days"],
];

const LAYER_KEY = /^(team|(team|weapon|ordnance|tacmod|hand|pose|speed|death|payload):[a-z0-9]{1,16})$/;
const GEAR = ["weapon", "ordnance", "tacmod"];

/** The sentence under the cards for one layer on its own. */
function describe(l: MapHeatLayer, all: boolean, when: string): ReactNode {
  const name = l.label.toLowerCase();
  if (GEAR.includes(l.group))
    return all ? (
      <>Everywhere <GearLabel name={l.label} /> was held, {when}: brighter where it is held most.</>
    ) : (
      <>Where <GearLabel name={l.label} /> is held more often than on the rest of the map, {when}: brighter = more often than usual.</>
    );
  if (l.group === "death")
    return all
      ? `Where players die, ${when} (estimated: the last spot before a player left the play area): brighter where most.`
      : `Where players die more often than the time spent there would suggest, ${when} (estimated deaths): brighter = more deaths for the time spent.`;
  return all
    ? `Everywhere players were ${name}, ${when}: brighter where most.`
    : `Where players are ${name} more often than on the rest of the map, ${when}: brighter = more often than usual.`;
}

const ZOOM_MAX = 8;

/** The large view of one map: the full-size minimap under the heat. Zoom with the buttons, a double click or
 * Ctrl + wheel (plain wheel once zoomed in, so the page still scrolls past it), drag to move; under the pointer the
 * value of the spot is read from the heat picture's own palette entries (heatRead.ts). */
function BigHeat({ map, heat, one, other, alt }: { map: string; heat: MapHeat | null; one: string; other: string; alt: string }) {
  const image = heat?.maps[map]?.image;
  const stage = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState({ z: 1, x: 0, y: 0 }); // x, y: the picture's top left against the stage's, in pixels
  const [entries, setEntries] = useState<Entries | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; moved: boolean } | null>(null);

  useEffect(() => setZoom({ z: 1, x: 0, y: 0 }), [map]);
  useEffect(() => {
    let current = true;
    setEntries(null);
    setTip(null);
    if (image) decodeEntries(image).then((e) => current && setEntries(e));
    return () => {
      current = false;
    };
  }, [image]);

  /** Zoom to `z` keeping the point (px, py) of the stage where it is; the picture always covers the stage. */
  const zoomTo = useCallback((z: number, px?: number, py?: number) => {
    setZoom((old) => {
      const base = inner.current;
      if (!base) return old;
      const w = base.offsetWidth;
      const h = base.offsetHeight;
      const next = Math.min(ZOOM_MAX, Math.max(1, z));
      const cx = px ?? w / 2;
      const cy = py ?? h / 2;
      const x = cx - ((cx - old.x) / old.z) * next;
      const y = cy - ((cy - old.y) / old.z) * next;
      return { z: next, x: Math.min(0, Math.max(w - w * next, x)), y: Math.min(0, Math.max(h - h * next, y)) };
    });
  }, []);

  const currentZoom = useRef(1);
  currentZoom.current = zoom.z;
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    // a listener of our own: React's wheel events are passive, and the page must not scroll while the map zooms
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey && currentZoom.current <= 1) return; // not zoomed in: the wheel scrolls the page
      e.preventDefault();
      const box = inner.current!.parentElement!.getBoundingClientRect();
      zoomTo(currentZoom.current * (e.deltaY < 0 ? 1.25 : 0.8), e.clientX - box.left, e.clientY - box.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomTo]);

  const local = (e: { clientX: number; clientY: number }) => {
    const box = inner.current!.parentElement!.getBoundingClientRect();
    return { x: e.clientX - box.left, y: e.clientY - box.top };
  };
  const onMove = (e: React.PointerEvent) => {
    const at = local(e);
    const d = drag.current;
    if (d && d.id === e.pointerId) {
      if (Math.abs(at.x - d.x) + Math.abs(at.y - d.y) > 3) d.moved = true;
      if (d.moved) {
        const w = inner.current!.offsetWidth;
        const h = inner.current!.offsetHeight;
        setZoom((old) => ({ z: old.z, x: Math.min(0, Math.max(w - w * old.z, old.x + at.x - d.x)), y: Math.min(0, Math.max(h - h * old.z, old.y + at.y - d.y)) }));
        d.x = at.x;
        d.y = at.y;
        setTip(null);
        return;
      }
    }
    if (!heat || !entries) return;
    const w = inner.current!.offsetWidth;
    const h = inner.current!.offsetHeight;
    const text = readOut(heat, map, entryAt(entries, (at.x - zoom.x) / (w * zoom.z), (at.y - zoom.y) / (h * zoom.z)), one, other);
    setTip(text ? { x: at.x, y: at.y, text } : null);
  };

  return (
    <div className="map-heat-big-stage" ref={stage}>
      <div className="map-heat-big-frame"
        onPointerDown={(e) => {
          if (e.button !== 0 || zoom.z === 1) return;
          drag.current = { id: e.pointerId, ...local(e), moved: false };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={onMove}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
        onPointerLeave={() => setTip(null)}
        onDoubleClick={(e) => {
          const at = local(e);
          zoomTo(zoom.z >= ZOOM_MAX ? 1 : zoom.z * 2, at.x, at.y);
        }}
        style={{ cursor: zoom.z > 1 ? "grab" : undefined }}>
        <div ref={inner} className={image ? "map-heat-big-inner has-heat" : "map-heat-big-inner"}
          style={{ transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.z})` }}>
          <img key={map} src={minimapUrl(map)} alt={`${title(map)} minimap`} decoding="async" draggable={false} />
          {image && <img className={zoom.z >= 3 ? "map-card-heat cells" : "map-card-heat"} src={image} alt={alt} draggable={false} />}
        </div>
        {tip && (
          <span className="map-heat-tip" style={{ left: tip.x, top: tip.y }} role="status">
            {tip.text}
          </span>
        )}
      </div>
      <div className="map-heat-zoom">
        <button type="button" className="secondary" onClick={() => zoomTo(zoom.z * 1.5)} disabled={zoom.z >= ZOOM_MAX} aria-label="Zoom in" title="Zoom in">+</button>
        <button type="button" className="secondary" onClick={() => zoomTo(zoom.z / 1.5)} disabled={zoom.z <= 1} aria-label="Zoom out" title="Zoom out">−</button>
        <button type="button" className="secondary" onClick={() => zoomTo(1)} disabled={zoom.z <= 1} title="Show the whole map">Reset</button>
      </div>
    </div>
  );
}

/** "Matches per map": a card per map, its minimap under the all-time heat of every counted match (counted once a
 * month on the server, map_heat.py). The heat is of both teams, or of one layer: a weapon, ordnance or tac mod, left- /
 * right-handed players, upside down / upright, a speed
 * band, the estimated deaths; "Payload" draws the payload's own speed or rollback along its route. One request
 * per choice, four small PNGs, kept by the answer cache (here, on the server and at Cloudflare), so going back to a
 * choice is instant. A layer opens on its "favoured spots" (where it is more than usual): everywhere it was looks much
 * the same for every piece of gear, the objective and the payload's route.
 * "Compare with" lays the chosen layer against any other one, each in its own colour where it is relatively more
 * often than the other; the swap button turns the two around (user, 2026-11-10).
 * The choice lives in the address (`heat`, `view`, `vs`, `map`), so a view can be linked. Until the first answer (or
 * if it fails) the cards show the plain minimap. Clicking a card's picture opens that map large under the cards
 * (BigHeat: zoom, drag, the value under the pointer); the map's name still leads to its matches. */
export function MapHeatCards({ byMap, total }: { byMap: Record<string, number>; total: number }) {
  const [params, setParams] = useSearchParams();
  const update = (changes: Record<string, string | null>) =>
    setParams(
      (old) => {
        const next = new URLSearchParams(old);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  const asked = (key: string) => (LAYER_KEY.test(params.get(key) ?? "") ? params.get(key)! : "");
  const layer = asked("heat") || "team";
  const view: MapHeatView = params.get("view") === "all" ? "all" : "favoured";
  const against = asked("vs");
  const days = HEAT_RANGES.find(([n]) => String(n) === params.get("days"))?.[0] ?? 0;
  const when = HEAT_RANGES.find(([n]) => n === days)![2];
  const big = params.get("map") && params.get("map")! in byMap ? params.get("map") : null;
  const setLayer = (key: string) => update({ heat: key === "team" ? null : key });
  const setBig = (map: string | null) => update({ map });

  const isPayload = layer.startsWith("payload:");
  const versus = against && against !== layer && !isPayload && !against.startsWith("payload:") ? against : ""; // nothing is compared with itself, or with the payload
  const heat = useApi(() => getMapHeat(layer, view, versus || undefined, days), `map-heat:${days}:${layer}:${versus ? `vs:${versus}` : layer === "team" || isPayload ? "" : view}`);
  const d = heat.data; // the previous choice's answer stays until the new one is there
  const layers = d?.layers ?? [];
  const labelOf = (key: string | null | undefined) =>
    key === "team" ? "Both teams" : HEAT_TEAMS.find(([k]) => k === key)?.[1] ?? layers.find((l) => l.key === key)?.label ?? "";
  const group = layers.find((l) => l.key === layer)?.group ?? "team";
  const inGroup = layers.filter((l) => l.group === group);
  const shown = layers.find((l) => l.key === d?.layer);
  const bigBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!big) return;
    bigBox.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && update({ map: null });
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [big]);
  const compared = d?.view === "compare" && d.against ? d.against : "";
  const what = compared ? `${labelOf(d?.layer)} vs ${labelOf(compared)}` : shown && shown.group !== "team" ? (shown.group === "payload" ? `payload ${shown.label.toLowerCase()}` : shown.label) : labelOf(d?.layer).toLowerCase() || "both teams";
  const counted = d?.matches ?? 0;
  const fromPoses = shown?.group === "pose" || compared.startsWith("pose:");
  const average = (m: string) => {
    const value = d?.view === "payload" ? d.maps[m]?.average : undefined;
    if (value == null) return null;
    if (d!.layer === "payload:back") return `rolling back ${pct(value)} of the time`;
    return `${value.toFixed(2)} m/s on average${d!.layer === "payload:moving" ? " while moving" : ""}`;
  };
  return (
    <>
      <div className="section-head map-heat-head">
        <h2>Matches per map</h2>
        {layers.length > 1 && (
          <div className="tabs" role="tablist" aria-label="All-time heatmap of">
            {HEAT_GROUPS.filter(([g]) => layers.some((l) => l.group === g)).map(([g, label]) => (
              <button key={g} role="tab" aria-selected={group === g} className={group === g ? "tab active" : "tab"}
                onClick={() => g !== group && setLayer(layers.find((l) => l.group === g)!.key)}>
                {label}
              </button>
            ))}
          </div>
        )}
        {(layers.length > 1 || days > 0) && (
          <label className="map-heat-against" title="Which matches the heatmaps are counted from">
            <select value={days} aria-label="Time range" onChange={(e) => update({ days: e.target.value === "0" ? null : e.target.value })}>
              {HEAT_RANGES.map(([n, label]) => (
                <option key={n} value={n}>{label}</option>
              ))}
            </select>
          </label>
        )}
        {layers.length > 1 && !isPayload && (
          <span className="map-heat-against">
            <label title="Lay the chosen heatmap against another one: each in its own colour where it is relatively more often than the other">
              Compare with{" "}
              <select value={versus} onChange={(e) => update({ vs: e.target.value || null })}>
                <option value="">nothing</option>
                <optgroup label="Teams">
                  {layer !== "team" && <option value="team">Both teams (everybody)</option>}
                  {HEAT_TEAMS.filter(([k]) => k !== layer).map(([k, label]) => (
                    <option key={k} value={k}>{label}</option>
                  ))}
                </optgroup>
                {HEAT_GROUPS.filter(([g]) => g !== "team" && g !== "payload" && layers.some((l) => l.group === g)).map(([g, label]) => (
                  <optgroup key={g} label={label}>
                    {layers.filter((l) => l.group === g && l.key !== layer).map((l) => (
                      <option key={l.key} value={l.key}>{l.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            {versus && (
              <button type="button" className="secondary map-heat-swap" title={`Swap: ${labelOf(versus)} compared with ${labelOf(layer)}`}
                aria-label="Swap the two heatmaps" onClick={() => update({ heat: versus === "team" ? null : versus, vs: layer })}>
                ⇄
              </button>
            )}
          </span>
        )}
      </div>
      {group !== "team" && (
        <div className="chips map-heat-gear">
          {inGroup.map((l) => (
            <button key={l.key} className={l.key === layer ? "chip active" : "chip"} aria-pressed={l.key === layer} onClick={() => setLayer(l.key)}
              title={l.share == null ? undefined : GEAR.includes(l.group) ? `Held ${pct(l.share)} of the time` : `${pct(l.share)} of the play time`}>
              <GearLabel name={l.label} />
            </button>
          ))}
          {!isPayload && !versus && (
            <span className="tabs map-heat-view" role="group" aria-label="What the heatmap shows">
              {HEAT_VIEWS.map(([v, label, hint]) => (
                <button key={v} className={view === v ? "tab active" : "tab"} aria-pressed={view === v} title={hint} onClick={() => update({ view: v === "all" ? v : null })}>
                  {label}
                </button>
              ))}
            </span>
          )}
        </div>
      )}
      <div className="map-cards">
        {Object.entries(byMap)
          .sort((a, b) => b[1] - a[1])
          .map(([m, n]) => {
            const image = d?.maps[m]?.image;
            return (
              <div key={m} className={big === m ? "map-card open" : "map-card"}>
                <button type="button" className={image ? "map-card-thumb has-heat" : "map-card-thumb"} aria-expanded={big === m}
                  title={big === m ? "Close the large view" : `Show ${title(m)} large`} onClick={() => setBig(big === m ? null : m)}>
                  <img src={minimapUrl(m, true)} alt={`${title(m)} heatmap`} loading="lazy" decoding="async" />
                  {image && <img className="map-card-heat" src={image} alt="" />}
                  <span className="map-card-zoom" aria-hidden="true">{big === m ? "−" : "+"}</span>
                </button>
                <Link to={`/matches?map=${m}`} className="map-card-name">
                  <strong>{title(m)}</strong>
                  <span className="muted">
                    {n.toLocaleString()} matches · {pct(n / total)}
                  </span>
                  {average(m) && <span className="map-card-average">Payload {average(m)}</span>}
                </Link>
              </div>
            );
          })}
      </div>
      {big && (
        <div className="panel map-heat-big" ref={bigBox}>
          <div className="section-head">
            <h3>
              {title(big)} <span className="muted">· {when} · {what}</span>
            </h3>
            <span>
              <Link to={`/matches?map=${big}`}>Matches on {title(big)}</Link>
              <button type="button" className="secondary map-heat-close" onClick={() => setBig(null)}>Close</button>
            </span>
          </div>
          <BigHeat map={big} heat={d} one={labelOf(d?.layer)} other={labelOf(compared)} alt={`Heatmap of ${what} on ${title(big)}, ${when}`} />
          <p className="muted map-heat-hint">
            {d && !d.maps[big]?.image ? `Nothing to show for this choice on ${title(big)}. ` : "Point at a spot to read its value. "}
            Double-click or Ctrl + wheel to zoom, drag to move.
          </p>
        </div>
      )}
      {d && Object.keys(d.maps).length === 0 && !heat.loading && (
        <p className="muted map-heat-note">
          Nothing to draw for this choice{fromPoses ? ": upside down is read from the 3D tracks, and too few matches have them yet" : d.building ? " yet: still being counted" : ": too little of it in the archive"}.
        </p>
      )}
      {d && Object.keys(d.maps).length > 0 && (
        <p className="muted map-heat-note">
          {compared ? (
            <>
              <span className="map-heat-swatch one" aria-hidden="true" /> where <GearLabel name={labelOf(d.layer)} /> is relatively more often,{" "}
              <span className="map-heat-swatch other" aria-hidden="true" /> where <GearLabel name={labelOf(compared)} /> is; {when}, each measured against its own total. Clear = about as often.
            </>
          ) : shown && shown.group === "payload" ? (
            <>
              <span className="map-heat-scale" aria-hidden="true" />{" "}
              {shown.key === "payload:back" ? (
                <>Share of its time the payload rolled back at each point of the route, while the push was on{d.scale && <>: {pct(d.scale.min)} (dark) to {pct(d.scale.max)} (pale)</>}.</>
              ) : shown.key === "payload:moving" ? (
                <>Average speed of the payload at each point of the route, only while it moves forward{d.scale && <>: {d.scale.min.toFixed(1)} m/s (dark) to {d.scale.max.toFixed(1)} m/s (pale)</>}.</>
              ) : (
                <>Average speed of the payload at each point of the route, the moments it stands still or rolls back included{d.scale && <>: {d.scale.min.toFixed(1)} m/s (dark = slow) to {d.scale.max.toFixed(1)} m/s (pale = fast)</>}.</>
              )}
            </>
          ) : shown && shown.group !== "team" ? (
            <>
              <span className="map-heat-scale" aria-hidden="true" /> {describe(shown, d.view === "all", when)}
            </>
          ) : (
            <>Heatmap of every match, {when}: each spot in the colour of the team that is there most (<span className="team-text blue">blue</span> / <span className="team-text orange">orange</span>), brighter where players are most.</>
          )}{" "}
          {fromPoses ? `From the ${counted.toLocaleString()} matches that have 3D tracks. ` : days > 0 && `From ${counted.toLocaleString()} matches. `}
          {d.building ? "Still being counted, more matches are added as it goes." : d.updated_on && `Updated once a ${days ? "day" : "month"}, last on ${d.updated_on}.`}
        </p>
      )}
    </>
  );
}
