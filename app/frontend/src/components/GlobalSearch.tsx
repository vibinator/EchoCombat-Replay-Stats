import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { search, type SearchResult } from "../api";
import { dateTime, int, playerPath, title } from "../format";

/** Top-bar search: players by name, or a match by "#id". Press "/" anywhere to focus it. */
export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        e.preventDefault();
        input.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const term = q.trim();
    // one letter matches nearly every player (the slowest search, the least useful); "#12" / "12" finds a match
    if (term.length < 2 && !/^#?\d+$/.test(term)) {
      setResult(null);
      return;
    }
    let current = true; // an answer for an older term never replaces a newer one
    const timer = setTimeout(
      () => search(term).then((r) => current && setResult(r)).catch(() => current && setResult(null)),
      250,
    );
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [q]);

  const options = [
    ...(result?.matches ?? []).map((m) => ({ key: `m${m.id}`, label: `Match #${m.id} · ${title(m.map)} · ${dateTime(m.started_at)}`, to: `/matches/${m.id}` })),
    ...(result?.players ?? []).map((p) => ({ key: p.user_id, label: `${p.name} · ${int(p.games)} games`, to: playerPath(p.user_id, p.name) })),
  ];

  function go(to: string) {
    setOpen(false);
    setQ("");
    navigate(to);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, options.length - 1));
    else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
    else if (e.key === "Enter") {
      if (options[active]) go(options[active].to);
      else if (q.trim()) go(`/players?q=${encodeURIComponent(q.trim())}`);
    } else if (e.key === "Escape") setOpen(false);
  }

  return (
    <div className="global-search" role="combobox" aria-expanded={open && options.length > 0} aria-haspopup="listbox">
      <input
        ref={input}
        type="search"
        maxLength={64} // the API refuses longer searches
        placeholder="Search players, #match or replay ID  ( / )"
        aria-label="Search players, match number or replay match id"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {open && options.length > 0 && (
        <ul className="suggestions" role="listbox">
          {options.map((o, i) => (
            <li key={o.key} role="option" aria-selected={i === active} className={i === active ? "active" : ""} onMouseDown={() => go(o.to)}>
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
