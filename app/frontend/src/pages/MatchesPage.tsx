import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { listMatches } from "../api";
import { MatchTable, Status } from "../components/common";
import { MatchCards } from "../components/MatchCards";
import { Skeleton } from "../components/ui";
import { MAPS, MAP_MODE, modeLabel, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const PAGE_SIZE = 24;
const FILTERS = ["map", "mode", "from", "to", "player", "min_players", "result", "player_name"] as const;

export function MatchesPage() {
  usePageTitle("Matches");
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get("offset") ?? 0);
  const view = params.get("view") === "list" ? "list" : "cards";
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? ""])) as Record<(typeof FILTERS)[number], string>;
  const result = useApi(
    () => listMatches({ ...filters, with_players: view === "cards" ? "true" : "", limit: PAGE_SIZE, offset }),
    params.toString(),
  );
  const [name, setName] = useState(filters.player_name);
  useEffect(() => setName(filters.player_name), [filters.player_name]);

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  }

  /** Map and mode are one choice: a mode means both of its maps, a map already implies its mode. */
  function pick(mode: string, map: string) {
    const next = new URLSearchParams(params);
    for (const [k, v] of [["mode", mode], ["map", map]]) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    next.delete("offset");
    setParams(next);
  }

  const total = result.data?.total ?? 0;
  const active = FILTERS.filter((k) => filters[k]).length;

  return (
    <section>
      <div className="section-head">
        <h1>Matches</h1>
        <div className="tabs" role="tablist" aria-label="View">
          {(["cards", "list"] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} className={view === v ? "tab active" : "tab"} onClick={() => set("view", v === "cards" ? "" : v)}>
              {title(v)}
            </button>
          ))}
        </div>
      </div>
      <div className="filters">
        <div className="map-picker" role="group" aria-label="Map and mode">
          {(["payload", "capture_point"] as const).map((md) => (
            <div key={md} className="map-group">
              <button
                className={filters.mode === md && !filters.map ? "map-chip head active" : "map-chip head"}
                aria-pressed={filters.mode === md && !filters.map}
                title={`Every ${modeLabel(md).toLowerCase()} map`}
                onClick={() => pick(filters.mode === md && !filters.map ? "" : md, "")}
              >
                {modeLabel(md)}
              </button>
              {MAPS.filter((m) => MAP_MODE[m] === md).map((m) => (
                <button
                  key={m}
                  className={filters.map === m ? "map-chip active" : "map-chip"}
                  aria-pressed={filters.map === m}
                  onClick={() => pick("", filters.map === m ? "" : m)}
                >
                  {title(m)}
                </button>
              ))}
            </div>
          ))}
        </div>
        <label>
          Result
          <select value={filters.result} onChange={(e) => set("result", e.target.value)}>
            <option value="">All</option>
            <option value="blue">Blue won</option>
            <option value="orange">Orange won</option>
            <option value="attack_win">Payload: attack won</option>
            <option value="defence_win">Payload: defence won</option>
            <option value="unknown">Winner unknown</option>
          </select>
        </label>
        <label>
          Min. players
          <select value={filters.min_players} onChange={(e) => set("min_players", e.target.value)}>
            <option value="">Any</option>
            {[2, 4, 6, 8, 10].map((n) => (
              <option key={n} value={n}>{n}+</option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" value={filters.from} onChange={(e) => set("from", e.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={filters.to} onChange={(e) => set("to", e.target.value)} />
        </label>
        <form
          className="filter-text"
          onSubmit={(e) => {
            e.preventDefault();
            set("player_name", name.trim());
          }}
        >
          <label>
            Player name
            <input type="search" maxLength={64} value={name} placeholder="contains…" onChange={(e) => setName(e.target.value)} onBlur={() => set("player_name", name.trim())} />
          </label>
        </form>
        {active > 0 && (
          <button className="link" onClick={() => setParams(view === "list" ? { view } : {})}>
            Clear filters ({active})
          </button>
        )}
      </div>

      {filters.player && <p className="note">Showing matches with one player.</p>}
      {result.loading && !result.data && <Skeleton lines={6} />}
      <Status loading={false} error={result.error} />
      {result.data && (
        <>
          <p className="muted">{total.toLocaleString()} matches</p>
          {view === "cards" ? <MatchCards matches={result.data.items} /> : <MatchTable matches={result.data.items} />}
          {total > PAGE_SIZE && (
            <div className="pager">
              <button className="secondary" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - PAGE_SIZE)))}>
                Previous
              </button>
              <span className="muted">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}
              </span>
              <button className="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => set("offset", String(offset + PAGE_SIZE))}>
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
