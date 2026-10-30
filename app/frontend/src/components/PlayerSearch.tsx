import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

export function PlayerSearch({ initial = "", large = false }: { initial?: string; large?: boolean }) {
  const [q, setQ] = useState(initial);
  const navigate = useNavigate();

  function submit(e: FormEvent) {
    e.preventDefault();
    navigate(`/players?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <form className={`search${large ? " large" : ""}`} onSubmit={submit} role="search">
      <input
        type="search"
        placeholder="Search player name"
        aria-label="Search player name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <button type="submit">Search</button>
    </form>
  );
}
