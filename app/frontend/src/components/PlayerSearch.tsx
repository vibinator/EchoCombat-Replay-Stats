import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { searchPlayers } from "../api";
import { playerPath } from "../format";
import { PlayerSuggest } from "./PlayerSuggest";

export function PlayerSearch({ initial = "", large = false }: { initial?: string; large?: boolean }) {
  const [q, setQ] = useState(initial);
  const navigate = useNavigate();

  function submit(e: FormEvent) {
    e.preventDefault();
    navigate(`/players?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <form className={`search${large ? " large" : ""}`} onSubmit={submit} role="search">
      <PlayerSuggest
        type="search"
        maxLength={64} // the API refuses longer searches
        placeholder="Search player name"
        ariaLabel="Search player name"
        value={q}
        onChange={setQ}
        search={(term) => searchPlayers(term, 8).then((r) => r.items)}
        onPick={(p) => navigate(playerPath(p.user_id, p.name))}
      />
      <button type="submit">Search</button>
    </form>
  );
}
