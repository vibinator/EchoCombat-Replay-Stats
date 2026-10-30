import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { listMatches } from "../api";
import { MatchTable, Status } from "../components/common";
import { MatchCards } from "../components/MatchCards";
import { Skeleton } from "../components/ui";
import { MAPS, title } from "../format";
import { useApi } from "../useApi";

const PAGE_SIZE = 24;
const FILTERS = ["map", "mode", "from", "to", "player", "private", "min_players", "result", "player_name"] as const;

export function MatchesPage() {
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
        <label>
          Map
          <select value={filters.map} onChange={(e) => set("map", e.target.value)}>
            <option value="">All</option>
            {MAPS.map((m) => (
              <option key={m} value={m}>{title(m)}</option>
            ))}
          </select>
        </label>
        <label>
          Mode
          <select value={filters.mode} onChange={(e) => set("mode", e.target.value)}>
            <option value="">All</option>
            <option value="capture_point">Capture point</option>
            <option value="payload">Payload</option>
          </select>
        </label>
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
          Match type
          <select value={filters.private} onChange={(e) => set("private", e.target.value)}>
            <option value="">All</option>
            <option value="false">Public</option>
            <option value="true">Private</option>
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
            <input type="search" value={name} placeholder="contains…" onChange={(e) => setName(e.target.value)} onBlur={() => set("player_name", name.trim())} />
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
