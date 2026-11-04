import { useEffect, useRef, useState, type KeyboardEvent } from "react";

export interface Suggestion {
  user_id: string;
  name: string;
  games: number;
}

const MIN_CHARS = 2;

/** A text box (or, with `multiline`, a box with one player per line) that lists matching players while you type.
 *  `search` finds them; picking one calls `onPick`, which decides what happens (fill in the id, open the profile).
 *  In a multi-line box the line the cursor is on is the one being searched and replaced. */
export function PlayerSuggest({
  value, onChange, search, onPick, multiline = false, placeholder, ariaLabel, type = "text", maxLength, autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  search: (q: string) => Promise<Suggestion[]>;
  /** Pick a suggestion. Omitted: its id replaces the text being typed. */
  onPick?: (p: Suggestion) => void;
  multiline?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  type?: "text" | "search";
  maxLength?: number;
  autoFocus?: boolean;
}) {
  const [caret, setCaret] = useState(value.length);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const seq = useRef(0);

  // The text being searched: the whole box, or the line under the cursor.
  const at = Math.min(caret, value.length);
  const lineStart = multiline && at > 0 ? value.lastIndexOf("\n", at - 1) + 1 : 0;
  const nextBreak = multiline ? value.indexOf("\n", at) : -1;
  const lineEnd = nextBreak === -1 ? value.length : nextBreak;
  const term = value.slice(lineStart, lineEnd).trim();

  useEffect(() => {
    if (term.length < MIN_CHARS) {
      setItems([]);
      return;
    }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      search(term)
        .then((r) => {
          if (mine !== seq.current) return; // a newer search is on its way
          setItems(r.slice(0, 8));
          setActive(-1);
        })
        .catch(() => mine === seq.current && setItems([]));
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  function pick(p: Suggestion) {
    setOpen(false);
    if (onPick) return onPick(p);
    if (multiline) onChange(value.slice(0, lineStart) + p.user_id + value.slice(lineEnd));
    else onChange(p.user_id);
  }

  function onKey(e: KeyboardEvent) {
    if (!open || items.length === 0) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (e.key === "ArrowDown" ? (a + 1) % items.length : (a <= 0 ? items.length : a) - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault(); // choose the highlighted player instead of submitting the form
      pick(items[active]);
    } else if (e.key === "Escape") setOpen(false);
  }

  const shared = {
    value,
    placeholder,
    "aria-label": ariaLabel,
    autoFocus,
    autoComplete: "off",
    onChange: (e: { target: { value: string; selectionStart: number | null } }) => {
      onChange(e.target.value);
      setCaret(e.target.selectionStart ?? e.target.value.length);
      setOpen(true);
    },
    onSelect: (e: { currentTarget: { selectionStart: number | null } }) => setCaret(e.currentTarget.selectionStart ?? 0),
    onKeyDown: onKey,
    onFocus: () => setOpen(true),
    onBlur: () => setTimeout(() => setOpen(false), 150), // after a click on a suggestion has landed
    role: "combobox",
    "aria-expanded": open && items.length > 0,
    "aria-autocomplete": "list" as const,
  };

  return (
    <div className="suggest">
      {multiline ? <textarea rows={3} {...shared} /> : <input type={type} maxLength={maxLength} {...shared} />}
      {open && items.length > 0 && (
        <ul className="suggest-list" role="listbox">
          {items.map((p, i) => (
            <li
              key={p.user_id}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault(); // keep the focus in the box
                pick(p);
              }}
            >
              <strong>{p.name}</strong>
              <span className="muted">{p.games.toLocaleString()} games</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
