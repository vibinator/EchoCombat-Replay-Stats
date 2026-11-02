import { Fragment, type ReactNode, useEffect, useState } from "react";
import {
  CONSOLE_ACHIEVEMENTS_CSV, forgetResponses, getConsoleAchievements, getConsoleLog, getConsoleOverview, getMe, getMergeSuggestions,
  getProcessingStatus, loginUrl, runConsole, searchConsolePlayers,
  type ConsoleLogEntry, type ConsoleOverview, type ConsolePlayer, type ProcessingStatus,
} from "../api";
import { SplitBar } from "../components/bars";
import { duration, int, num, pct, playerPath } from "../format";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { GENERIC_ICON, IconEditor, IMG } from "../components/IconEditor";
import { useApi, useWhileVisible } from "../useApi";

type Field = {
  key: string;
  label: string;
  kind?: "text" | "date" | "check" | "list";
  hint?: string;
};

interface Command {
  name: string; // the admin.bat command the server runs
  label: string;
  help: string;
  fields?: Field[];
  /** asked before running, like the console's "[y/N]" */
  confirm?: (values: Record<string, string>) => string | null;
  /** a page of its own instead of a command form */
  view?: "achievements" | "dashboard" | "players" | "hidden-stats" | "log";
}

const lines = (text = "") =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

/** The admin.bat menu, plus the Console's own views. Who gets access is managed on the Permissions page. */
const GROUPS: { title: string; commands: Command[] }[] = [
  {
    title: "Overview",
    commands: [
      { name: "dashboard", label: "Dashboard", help: "", view: "dashboard" },
      { name: "log", label: "Audit log", help: "", view: "log" },
    ],
  },
  {
    title: "Players",
    commands: [
      { name: "players", label: "Player tools", help: "", view: "players" },
      {
        name: "merge",
        label: "Merge player records",
        help: "For one person who appears under several player ids. Their replays are read again, so the merge can always be undone.",
        fields: [
          { key: "main", label: "Player to keep", hint: "Name or id" },
          {
            key: "others",
            label: "Records to merge into it",
            kind: "list",
            hint: "One name or id per line",
          },
        ],
        confirm: (v) => `Merge ${lines(v.others).length} record(s) into ${v.main}?`,
      },
      {
        name: "merges",
        label: "List merges",
        help: "Every merge, newest first.",
      },
      {
        name: "unmerge",
        label: "Undo a merge",
        help: "Make a merged record a separate player again.",
        fields: [{ key: "alias", label: "Merged id", hint: "From “List merges”" }],
        confirm: (v) => `Undo the merge of ${v.alias}?`,
      },
    ],
  },
  {
    title: "Website",
    commands: [{ name: "hidden-stats", label: "Hide stats from players", help: "", view: "hidden-stats" }],
  },
  {
    title: "Replays",
    commands: [
      {
        name: "status",
        label: "Status and import progress",
        help: "Import progress, replay counts, failures and players, as text (the Dashboard shows the same live).",
      },
      {
        name: "scan",
        label: "Scan the replay folder",
        help: "Look for new and changed replay files now. The server also does this every few minutes.",
      },
      {
        name: "reprocess",
        label: "Re-process a replay",
        help: "Read one replay again, for example after an update.",
        fields: [{ key: "replay", label: "Replay", hint: "Replay id or part of its file path" }],
      },
      {
        name: "repair",
        label: "Repair a replay",
        help: "Read one damaged or incomplete replay again in repair mode, keeping every part that can be read.",
        fields: [{ key: "replay", label: "Replay", hint: "Replay id or part of its file path" }],
      },
      {
        name: "repair-failed",
        label: "Repair all failed replays",
        help: "Try repair mode once on every damaged or incomplete replay.",
        confirm: () => "Repair every damaged or incomplete replay?",
      },
      {
        name: "repair-aggressive",
        label: "Aggressively repair a replay",
        help: "For broken replay data that repair mode could not fix: rebuilds wiped zip headers, takes damaged parts from the zip's second copy of the frames and keeps every frame that reads correctly. Nothing is guessed.",
        fields: [{ key: "replay", label: "Replay", hint: "Replay id or part of its file path" }],
      },
      {
        name: "repair-aggressive-failed",
        label: "Aggressive repair of broken replays",
        help: "Try aggressive repair once on every broken replay that repair mode could not fix.",
        confirm: () => "Aggressively repair every broken replay that repair mode could not fix?",
      },
      {
        name: "cannot-repair",
        label: "Replays that cannot be repaired",
        help: "Failed replays that repair cannot fix. Hiding them leaves them out of the failed lists and counts; nothing is deleted.",
        fields: [{ key: "hide", label: "Hide them", kind: "check" }],
        confirm: (v) => (v.hide ? "Hide every failed replay that cannot be repaired?" : null),
      },
      {
        name: "hidden",
        label: "Hidden replays",
        help: "Replays hidden from the failed lists. Leave the fields empty to list them.",
        fields: [
          { key: "unhide", label: "Show one again", hint: "File path exactly as listed" },
          { key: "unhide_all", label: "Show all of them again", kind: "check" },
        ],
        confirm: (v) => (v.unhide_all ? "Show every hidden replay again?" : v.unhide ? `Show ${v.unhide} again?` : null),
      },
      {
        name: "reprocess-all",
        label: "Re-process every replay",
        help: "Scan the folder, then read the whole archive again. This takes hours; current results stay on the website until each replay is replaced.",
        confirm: () => "Re-process EVERY replay? This takes several hours.",
      },
    ],
  },
  {
    title: "Achievements",
    commands: [
      {
        name: "export-achievements",
        label: "Export achievements and challenges",
        help: "Every achievement and challenge with the rule to win it, as shown on the website.",
        view: "achievements",
      },
      {
        name: "challenge",
        label: "Launch date and challenge period",
        help:
          "The start date is the launch: until then achievements and challenges show “Coming soon”, and only matches from that day count. " +
          "Leave both dates empty to see the current period; an empty date is kept as it is.",
        fields: [
          { key: "start", label: "Start", kind: "date" },
          { key: "end", label: "End (optional)", kind: "date" },
          { key: "clear", label: "Remove both dates", kind: "check" },
        ],
        confirm: (v) =>
          v.clear ? "Remove both dates? Achievements go back to “Coming soon”." : v.start ? `Set the launch date to ${v.start}?` : null,
      },
    ],
  },
  {
    title: "Discord access",
    commands: [
      {
        name: "discord-check",
        label: "Check a member's access",
        help: "Whether one person is an Admin, gets the Preview and the Console page. To change who gets what, use the Permissions page.",
        fields: [{ key: "user_id", label: "Discord user id", hint: "In Discord: right-click the person > Copy User ID" }],
      },
    ],
  },
];

const ALL_COMMANDS = GROUPS.flatMap((g) => g.commands);
/** The menu label of a command, for the audit log; commands run from a view (hide-stats) get a name of their own. */
const COMMAND_LABELS: Record<string, string> = {
  ...Object.fromEntries(ALL_COMMANDS.map((c) => [c.name, c.label])),
  "hide-stats": "Hide stats from players",
  find: "Find a player",
  "preview-roles": "Discord preview roles",
  "admin-roles": "Discord admin roles",
  "admin-users": "Discord admin users",
};

/** What the server expects: text, true / false, and `others` as a list. An empty date is left out (= keep). */
function toArgs(fields: Field[], values: Record<string, string>): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key] ?? "";
    if (f.kind === "check") args[f.key] = v === "1";
    else if (f.kind === "list") args[f.key] = lines(v);
    else if (f.kind !== "date" || v) args[f.key] = v.trim();
  }
  return args;
}

interface Result {
  id: number;
  label: string;
  ok: boolean;
  output: string;
  at: string;
}

/** What a view needs from the page: run a command (its output goes to Results), open another command's form. */
interface ConsoleApi {
  run: (command: string, label: string, args: Record<string, unknown>) => Promise<boolean>;
  open: (command: string, values?: Record<string, string>) => void;
  version: number; // goes up after every command: views load their data again
}

/** admin.bat on the website (D45). Only for people named in ECHOVR_DISCORD_PREVIEW_ROLES; the server checks every
 * command, this page only decides what to show. */
export function ConsolePage() {
  const me = useApi(getMe, "me");
  if (!me.data) return <Status loading={me.loading} error={me.error} />;
  const user = me.data.user;
  if (!user?.console)
    return (
      <section>
        <h1>Console</h1>
        <EmptyState title="No access">
          {!me.data.enabled ? (
            "Discord login is not set up on this server."
          ) : user ? (
            <>You are logged in as {user.name}, but you do not have access to the console.</>
          ) : (
            <>
              The console is for site staff. <a href={loginUrl("/console")}>Log in with Discord</a>
            </>
          )}
        </EmptyState>
      </section>
    );
  return <Console />;
}

function Console() {
  const [selected, setSelected] = useState<Command>(GROUPS[0].commands[0]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[]>([]);
  const [filter, setFilter] = useState("");
  const set = (key: string, value: string) => setValues((v) => ({ ...v, [key]: value }));

  async function execute(command: string, label: string, args: Record<string, unknown>): Promise<boolean> {
    setBusy(true);
    const add = (ok: boolean, output: string) =>
      setResults((prev) => [{ id: Date.now(), label, ok, output, at: new Date().toLocaleTimeString() }, ...prev].slice(0, 30));
    try {
      const r = await runConsole(command, args);
      add(r.ok, r.output || "Done.");
      forgetResponses(); // other pages show the change straight away
      return r.ok;
    } catch (e) {
      add(false, (e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function open(name: string, preset: Record<string, string> = {}) {
    const command = ALL_COMMANDS.find((c) => c.name === name);
    if (!command) return;
    setSelected(command);
    setValues(preset);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    const question = selected.confirm?.(values);
    if (question && !window.confirm(question)) return;
    await execute(selected.name, selected.label, toArgs(selected.fields ?? [], values));
  }

  const api: ConsoleApi = { run: execute, open, version: results.length };
  const term = filter.trim().toLowerCase();
  const groups = GROUPS.map((g) => ({
    ...g,
    commands: g.commands.filter((c) => !term || `${g.title} ${c.label} ${c.help}`.toLowerCase().includes(term)),
  })).filter((g) => g.commands.length > 0);

  return (
    <section>
      <div className="console-title">
        <h1>Console</h1>
        <p className="muted">
          Commands run on the server and apply straight away. Every command is written to the audit log with your Discord name.
        </p>
      </div>
      <div className="console-layout">
        <nav className="console-menu" aria-label="Console">
          <input
            type="search"
            className="console-filter"
            placeholder="Find a command"
            aria-label="Find a command"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {groups.map((g) => (
            <div key={g.title}>
              <h2>{g.title}</h2>
              {g.commands.map((c) => (
                <button
                  key={c.name}
                  className={c === selected ? "active" : "secondary"}
                  aria-current={c === selected}
                  onClick={() => open(c.name)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          ))}
          {groups.length === 0 && <p className="muted">No command matches.</p>}
        </nav>
        <div className="console-main">
          {selected.view === "dashboard" ? (
            <Dashboard api={api} />
          ) : selected.view === "players" ? (
            <PlayerTools api={api} />
          ) : selected.view === "hidden-stats" ? (
            <HiddenStats api={api} />
          ) : selected.view === "log" ? (
            <AuditLog api={api} />
          ) : selected.view === "achievements" ? (
            <AchievementExport />
          ) : (
            <form
              className="panel console-form"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <h2>{selected.label}</h2>
              <p className="muted">{selected.help}</p>
              {selected.fields?.map((f) =>
                f.kind === "check" ? (
                  <label key={f.key} className="console-check">
                    <input type="checkbox" checked={values[f.key] === "1"} onChange={(e) => set(f.key, e.target.checked ? "1" : "")} />
                    {f.label}
                  </label>
                ) : (
                  <label key={f.key} className="console-field">
                    <span>{f.label}</span>
                    {f.kind === "list" ? (
                      <textarea rows={3} placeholder={f.hint} value={values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} />
                    ) : (
                      <input
                        type={f.kind === "date" ? "date" : "text"}
                        placeholder={f.hint}
                        value={values[f.key] ?? ""}
                        onChange={(e) => set(f.key, e.target.value)}
                      />
                    )}
                  </label>
                ),
              )}
              <div>
                <button type="submit" disabled={busy}>
                  {busy ? "Running…" : "Run"}
                </button>
              </div>
            </form>
          )}
          {selected.name === "merge" && (
            <MergeSuggestions
              version={results.length}
              onUse={(keep, others) => {
                setValues({ main: keep, others: others.join("\n") });
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          )}
          {results.length > 0 && (
            <div className="section-head">
              <h2>Results</h2>
              <button className="secondary" onClick={() => setResults([])}>
                Clear
              </button>
            </div>
          )}
          {results.map((r) => (
            <OutputPanel key={r.id} label={r.label} ok={r.ok} at={r.at} output={r.output} />
          ))}
        </div>
      </div>
    </section>
  );
}

/** What a command printed, with a Copy button. */
function OutputPanel({ label, ok, at, output }: { label: string; ok: boolean; at: string; output: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <article className={`panel console-output${ok ? "" : " failed"}`}>
      <header>
        <strong>{label}</strong>
        <span className={ok ? "tag" : "tag error"}>{ok ? "Done" : "Failed"}</span>
        <span className="muted">{at}</span>
        <button
          type="button"
          className="secondary small"
          onClick={async () => {
            await navigator.clipboard.writeText(output);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </header>
      <pre>{output}</pre>
    </article>
  );
}

const when = (iso: string) => new Date(iso).toLocaleString();

// --- Dashboard ----------------------------------------------------------------------------------

/** Live: processing progress (the Status page's answer) and the console's own facts, every 10 s while visible. */
function Dashboard({ api }: { api: ConsoleApi }) {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [overview, setOverview] = useState<ConsoleOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState<Date | null>(null);
  const load = () =>
    Promise.all([getProcessingStatus(), getConsoleOverview()]).then(
      ([s, o]) => {
        setStatus(s);
        setOverview(o);
        setError(null);
        setAt(new Date());
      },
      (e: Error) => setError(e.message),
    );
  useWhileVisible(load, 10_000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (api.version) void load(); // after a command (the first load is the polling's)
  }, [api.version]);

  if (!status || !overview) return <Status loading={!error} error={error} />;
  const c = status.counts;
  const total = c.queued + c.processing + c.done + c.failed;
  const finished = c.done + c.failed;
  const waiting = c.queued + c.processing;
  const winLoss = overview.stat_groups.find((g) => g.key === "win_loss");
  const scan = status.scan;

  return (
    <div className="console-view">
      <div className="section-head">
        <h2>Dashboard</h2>
        <span className="muted">{error ? `Could not refresh: ${error}` : at && `Updated ${at.toLocaleTimeString()} · every 10 s`}</span>
      </div>

      <div className="panel dash-progress">
        <div className="dash-progress-head">
          <strong>Import {total ? pct(finished / total) : "–"}</strong>
          <span className="muted">
            {int(finished)} of {int(total)} replays
            {status.redo > 0 && ` · ${int(status.redo)} being redone after an update`}
          </span>
        </div>
        <SplitBar
          percentages={false}
          parts={[
            { label: "Done", value: c.done, color: "var(--ok)", detail: int(c.done) },
            { label: "Failed", value: c.failed, color: "var(--bad)", detail: int(c.failed) },
            { label: "Processing", value: c.processing, color: "var(--chart-1)", detail: int(c.processing) },
            { label: "Queued", value: c.queued, color: "var(--line)", detail: int(c.queued) },
          ]}
        />
        <span className="muted">
          {waiting
            ? `${num(status.rate_per_min, 1)} replays/min · ${status.eta_min != null ? `about ${duration(status.eta_min * 60)} left` : "estimating time left"} · ${status.busy}/${status.workers} workers busy`
            : `Nothing waiting · ${status.workers} workers idle`}
        </span>
      </div>

      <div className="cards dash-cards">
        <DashCard label="Replay folder" value={scan.reachable === false ? "Unreachable" : scan.scanning ? "Scanning…" : "Reachable"} bad={scan.reachable === false}>
          {scan.error ? <span className="error-text">{scan.error}</span> : scan.last_scan_at && <>Last scan {when(scan.last_scan_at)} · {int(scan.files)} files</>}
          <button type="button" className="secondary small" onClick={() => api.run("scan", "Scan the replay folder", {})}>Scan now</button>
        </DashCard>
        <DashCard label="Failed replays" value={int(c.failed)} bad={overview.repairable > 0}>
          {overview.repairable > 0 && <>{int(overview.repairable)} can be repaired · </>}
          {overview.aggressive_repairable > 0 && <>{int(overview.aggressive_repairable)} for aggressive repair · </>}
          {int(overview.cannot_repair)} cannot · {int(overview.hidden_replays)} hidden
          {overview.repairable > 0 && (
            <button type="button" className="secondary small" onClick={() => api.open("repair-failed")}>Repair…</button>
          )}
          {overview.repairable === 0 && overview.aggressive_repairable > 0 && (
            <button type="button" className="secondary small" onClick={() => api.open("repair-aggressive-failed")}>Aggressive repair…</button>
          )}
        </DashCard>
        <DashCard label="Players" value={int(overview.players)}>
          {int(overview.merges)} merges
          <button type="button" className="secondary small" onClick={() => api.open("players")}>Player tools</button>
        </DashCard>
        <DashCard label="Achievements" value={overview.challenge.launched ? "Live" : "Coming soon"}>
          {overview.challenge.start ? `From ${overview.challenge.start}${overview.challenge.end ? ` to ${overview.challenge.end}` : ""}` : "No launch date set"}
          <button type="button" className="secondary small" onClick={() => api.open("challenge")}>Change</button>
        </DashCard>
        {winLoss && (
          <DashCard label="Win-loss stats" value={winLoss.hidden ? "Hidden" : "Shown"}>
            {winLoss.players.length > 0 ? `Hidden for ${winLoss.players.length} player(s)` : "No player hidden one by one"}
            <button type="button" className="secondary small" onClick={() => api.open("hidden-stats")}>Manage</button>
          </DashCard>
        )}
        <DashCard label="Version" value={status.versions.parser}>
          stats {status.versions.stats}
        </DashCard>
      </div>

      {status.current.length > 0 && (
        <div className="panel">
          <h3>Processing now</h3>
          <ul className="dash-list">
            {status.current.map((r) => (
              <li key={r.replay_id}>
                <code>{r.source_path}</code> <span className="muted">{duration(r.seconds)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="section-head">
        <h3>Latest commands</h3>
        <button type="button" className="secondary small" onClick={() => api.open("log")}>Audit log</button>
      </div>
      <LogTable rows={overview.recent} compact />
    </div>
  );
}

function DashCard({ label, value, bad, children }: { label: string; value: string; bad?: boolean; children?: ReactNode }) {
  return (
    <div className={`card dash-card${bad ? " bad" : ""}`}>
      <span className="label">{label}</span>
      <strong>{value}</strong>
      <span className="muted dash-card-detail">{children}</span>
    </div>
  );
}

// --- Player tools -------------------------------------------------------------------------------

function usePlayerSearch(version: number) {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTerm(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  const found = useApi(() => (term ? searchConsolePlayers(term) : Promise.resolve([] as ConsolePlayer[])), `console-players|${term}|${version}`);
  return { q, setQ, term, found };
}

/** Search a player, then act on the result: profile, win-loss, merges. */
function PlayerTools({ api }: { api: ConsoleApi }) {
  const { q, setQ, term, found } = usePlayerSearch(api.version);
  return (
    <div className="console-view">
      <div className="panel console-form">
        <h2>Player tools</h2>
        <p className="muted">Search by name or player id, then act on a player straight from the result.</p>
        <input type="search" placeholder="Name or player id" aria-label="Find a player" value={q} autoFocus onChange={(e) => setQ(e.target.value)} />
      </div>
      <Status loading={found.loading && !found.data} error={found.error} />
      {term && found.data?.length === 0 && <p className="muted">No player matches “{term}”.</p>}
      <div className="player-results">
        {found.data?.map((p) => (
          <article key={p.user_id} className="panel player-result">
            <header>
              <a href={playerPath(p.user_id, p.name)} target="_blank" rel="noopener noreferrer">
                <strong>{p.name}</strong>
              </a>
              <code>{p.user_id}</code>
              {p.win_loss_hidden && <span className="tag">win-loss hidden</span>}
              {p.merged_into && <span className="tag">merged into {p.merged_into.name}</span>}
            </header>
            <span className="muted">
              {int(p.games)} games · seen {p.first_seen_at.slice(0, 10)} – {p.last_seen_at.slice(0, 10)}
              {p.merged_ids.length > 0 && ` · has ${p.merged_ids.length} merged record(s): ${p.merged_ids.map((m) => m.name).join(", ")}`}
            </span>
            <div className="player-actions">
              <button
                type="button"
                className="secondary small"
                onClick={() => {
                  const hide = !p.win_loss_hidden;
                  if (!window.confirm(`${hide ? "Hide" : "Show"} ${p.name}'s win-loss stats${hide ? " from everyone except logged-in admins" : " again"}?`)) return;
                  api.run("hide-stats", `${hide ? "Hide" : "Show"} win-loss: ${p.name}`, { [hide ? "hide_win_loss" : "show_win_loss"]: true, player: p.user_id });
                }}
              >
                {p.win_loss_hidden ? "Show win-loss" : "Hide win-loss"}
              </button>
              {p.merged_into ? (
                <button type="button" className="secondary small" onClick={() => api.open("unmerge", { alias: p.user_id })}>
                  Undo merge…
                </button>
              ) : (
                <>
                  <button type="button" className="secondary small" onClick={() => api.open("merge", { main: p.user_id })}>
                    Keep, merge others into it…
                  </button>
                  <button type="button" className="secondary small" onClick={() => api.open("merge", { others: p.user_id })}>
                    Merge into another…
                  </button>
                </>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

// --- Hidden stats -------------------------------------------------------------------------------

/** The site-wide switch and the players hidden one by one, per stat group. */
function HiddenStats({ api }: { api: ConsoleApi }) {
  const overview = useApi(getConsoleOverview, `console-overview|${api.version}`);
  const { q, setQ, term, found } = usePlayerSearch(api.version);
  if (!overview.data) return <Status loading={overview.loading} error={overview.error} />;
  return (
    <div className="console-view">
      {overview.data.stat_groups.map((g) => {
        const flag = (hide: boolean) => ({ [hide ? `hide_${g.key}` : `show_${g.key}`]: true });
        return (
          <div key={g.key} className="panel console-form">
            <h2>Hide stats from players</h2>
            <p className="muted">Against pub stomping: hidden stats are left out of the website for everyone except logged-in admins. {g.label}.</p>

            <div className="hidden-switch">
              <div>
                <strong>Site-wide</strong>
                <span className={g.hidden ? "tag error" : "tag"}>{g.hidden ? "Hidden for everyone" : "Shown"}</span>
              </div>
              <button
                type="button"
                className={g.hidden ? "" : "secondary"}
                onClick={() => {
                  if (!window.confirm(g.hidden ? "Show win-loss stats to everyone again?" : "Hide win-loss stats from everyone except logged-in admins?")) return;
                  api.run("hide-stats", g.hidden ? "Show win-loss (site-wide)" : "Hide win-loss (site-wide)", flag(!g.hidden));
                }}
              >
                {g.hidden ? "Show for everyone" : "Hide for everyone"}
              </button>
            </div>

            <h3>Hidden for these players</h3>
            {g.hidden && <p className="muted">Hidden site-wide right now, so this list only matters once it is shown again.</p>}
            {g.players.length === 0 ? (
              <p className="muted">None.</p>
            ) : (
              <ul className="hidden-players">
                {g.players.map((p) => (
                  <li key={p.user_id}>
                    <a href={playerPath(p.user_id, p.name)} target="_blank" rel="noopener noreferrer">{p.name}</a>
                    <code>{p.user_id}</code>
                    <button
                      type="button"
                      className="secondary small"
                      onClick={() => {
                        if (!window.confirm(`Show ${p.name}'s win-loss stats again?`)) return;
                        api.run("hide-stats", `Show win-loss: ${p.name}`, { ...flag(false), player: p.user_id });
                      }}
                    >
                      Show again
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <label className="console-field">
              <span>Hide for another player</span>
              <input type="search" placeholder="Name or player id" value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
            {term && found.data?.length === 0 && <p className="muted">No player matches “{term}”.</p>}
            {term && (found.data?.length ?? 0) > 0 && (
              <ul className="hidden-players">
                {found.data!.filter((p) => !p.merged_into).slice(0, 8).map((p) => (
                  <li key={p.user_id}>
                    <span>{p.name}</span>
                    <code>{p.user_id}</code>
                    <span className="muted">{int(p.games)} games</span>
                    {p.win_loss_hidden ? (
                      <span className="tag">already hidden</span>
                    ) : (
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => {
                          if (!window.confirm(`Hide ${p.name}'s win-loss stats from everyone except logged-in admins?`)) return;
                          api.run("hide-stats", `Hide win-loss: ${p.name}`, { ...flag(true), player: p.user_id }).then((ok) => ok && setQ(""));
                        }}
                      >
                        Hide
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

// --- Audit log ----------------------------------------------------------------------------------

function argsText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => (v === true ? k.replace(/_/g, " ") : `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") : String(v)}`))
    .join(" · ");
}

function LogTable({ rows, compact }: { rows: ConsoleLogEntry[]; compact?: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  if (rows.length === 0) return <p className="muted">No commands yet.</p>;
  return (
    <TableWrap>
      <table className="stack console-log">
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Command</th>
            {!compact && <th>Details</th>}
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <Fragment key={r.id}>
              <tr className="log-row" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                <td data-label="When" className="nowrap">{when(r.at)}</td>
                <td data-label="Who">
                  {r.who} {r.source === "admin.bat" && <span className="tag">admin.bat</span>}
                </td>
                <td data-label="Command">{COMMAND_LABELS[r.command] ?? r.command}</td>
                {!compact && <td data-label="Details" className="muted">{argsText(r.args) || "–"}</td>}
                <td data-label="Result">
                  <span className={r.ok ? "tag" : "tag error"}>{r.ok ? "Done" : "Failed"}</span>
                </td>
              </tr>
              {open === r.id && (
                <tr className="log-output">
                  <td colSpan={compact ? 4 : 5}>
                    {compact && argsText(r.args) && <p className="muted">{argsText(r.args)}</p>}
                    <pre>{r.output || "(no output)"}</pre>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

/** Who ran which command and when, from the website or admin.bat; click a row for its output. */
function AuditLog({ api }: { api: ConsoleApi }) {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [more, setMore] = useState<ConsoleLogEntry[]>([]);
  const [end, setEnd] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setTerm(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    setMore([]);
    setEnd(false);
  }, [term, api.version]);
  const first = useApi(() => getConsoleLog(term), `console-log|${term}|${api.version}`);
  const rows = [...(first.data ?? []), ...more];

  async function loadMore() {
    const last = rows[rows.length - 1];
    if (!last) return;
    const next = await getConsoleLog(term, last.id);
    setMore((m) => [...m, ...next]);
    if (next.length < 100) setEnd(true);
  }

  return (
    <div className="console-view">
      <div className="panel console-form">
        <h2>Audit log</h2>
        <p className="muted">Every command run on this page or with admin.bat, newest first. Click a row to see what it printed.</p>
        <input type="search" placeholder="Filter by command, person or player" aria-label="Filter the audit log" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Status loading={first.loading && !first.data} error={first.error} />
      {first.data && <LogTable rows={rows} />}
      {first.data && first.data.length === 100 && !end && (
        <div className="pager">
          <button type="button" className="secondary" onClick={loadMore}>Older</button>
        </div>
      )}
    </div>
  );
}

/** Player records that used the same name, as candidates for the merge form above. Only suggestions: "Use" fills in
 * the form, the merge itself still needs Run and its confirmation. Reloaded after every command (`version`). */
function MergeSuggestions({ version, onUse }: { version: number; onUse: (keep: string, others: string[]) => void }) {
  const list = useApi(getMergeSuggestions, `merge-suggestions-${version}`);
  const [q, setQ] = useState("");
  const term = q.trim().toLowerCase();
  const groups = (list.data ?? []).filter(
    (g) => !term || g.players.some((p) => `${p.name} ${p.user_id} ${p.names.join(" ")}`.toLowerCase().includes(term)),
  );

  return (
    <div className="panel console-form merge-suggestions">
      <h2>Suggestions</h2>
      <p className="muted">
        Player records that used the same name (ignoring case and punctuation, including names used earlier). Check before merging: two
        people can share a name. Records that played in the same match are flagged and listed last.
      </p>
      <input type="search" placeholder="Filter by name or id" aria-label="Filter suggestions" value={q} onChange={(e) => setQ(e.target.value)} />
      <Status loading={list.loading && !list.data} error={list.error} />
      {list.data && (
        <p className="muted">
          {groups.length === list.data.length ? `${groups.length} suggestions` : `${groups.length} of ${list.data.length} suggestions`}
        </p>
      )}
      {list.data?.length === 0 && <p className="muted">No records share a name.</p>}
      {groups.map((g) => {
        const others = g.players.filter((p) => p.user_id !== g.keep).map((p) => p.user_id);
        return (
          <article key={g.players.map((p) => p.user_id).join(",")} className="merge-suggestion">
            <header>
              <strong>{g.name}</strong>
              <span className="tag">{g.exact ? "Same name" : "Similar name"}</span>
              {g.played_together > 0 && (
                <span className="tag error" title="Two of these records were in the same match: probably different people">
                  Played together in {g.played_together} match{g.played_together === 1 ? "" : "es"}
                </span>
              )}
              <button type="button" className="secondary" onClick={() => onUse(g.keep, others)}>
                Use
              </button>
            </header>
            <TableWrap>
              <table className="stack">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Id</th>
                    <th className="num">Games</th>
                    <th>Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {g.players.map((p) => (
                    <tr key={p.user_id}>
                      <td data-label="Player">
                        <a href={playerPath(p.user_id, p.name)} target="_blank" rel="noopener noreferrer">
                          {p.name}
                        </a>
                        {p.user_id === g.keep && <span className="tag">keep</span>}
                        {p.merged_ids > 0 && <span className="muted"> +{p.merged_ids} merged</span>}
                        {p.names.length > 0 && <div className="muted">also: {p.names.join(", ")}</div>}
                      </td>
                      <td data-label="Id">
                        <code>{p.user_id}</code>
                      </td>
                      <td data-label="Games" className="num">
                        {p.games.toLocaleString()}
                      </td>
                      <td data-label="Seen">
                        {p.first_seen_at.slice(0, 10)} – {p.last_seen_at.slice(0, 10)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </article>
        );
      })}
    </div>
  );
}

/** Name + rule for every achievement and challenge: copy (pastes as two columns into Excel / Sheets) or CSV. */
function AchievementExport() {
  const [version, setVersion] = useState(0); // an icon change loads the list again
  const list = useApi(getConsoleAchievements, `console-achievements-${version}`);
  const [editing, setEditing] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [copied, setCopied] = useState(false);
  const term = q.trim().toLowerCase();
  const items = (list.data ?? []).filter((r) => !term || `${r.name} ${r.rule}`.toLowerCase().includes(term));

  async function copy() {
    const text = ["Name\tHow to win it", ...items.map((r) => `${r.name}\t${r.rule}`)].join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="panel console-form">
      <h2>Export achievements and challenges</h2>
      <p className="muted">
        Every achievement and challenge with the rule to win it, exactly as the website shows it. Click an icon to change it or set it back
        to the original.
      </p>
      <div className="filters">
        <input type="search" placeholder="Filter" aria-label="Filter achievements" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="secondary" type="button" disabled={!items.length} onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <a className="button" href={CONSOLE_ACHIEVEMENTS_CSV} download>
          Download CSV
        </a>
      </div>
      {editing !== null && list.data?.some((r) => r.id === editing) && (
        <IconEditor
          row={list.data.find((r) => r.id === editing)!}
          onDone={(changed) => {
            if (changed) setVersion((v) => v + 1);
            else setEditing(null);
          }}
        />
      )}
      <Status loading={list.loading} error={list.error} />
      {list.data && (
        <>
          <p className="muted">
            {items.length} of {list.data.length}
            {term && " (Copy takes the filtered list; the CSV always has all of them)"}
          </p>
          <TableWrap>
            <table className="stack">
              <thead>
                <tr>
                  <th>Icon</th>
                  <th>Name</th>
                  <th>How to win it</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td data-label="Icon">
                      <button
                        className="icon-choice"
                        title="Change icon"
                        onClick={() => {
                          setEditing(r.id);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                      >
                        <img src={IMG + (r.icon ?? GENERIC_ICON)} alt={`Change icon for ${r.name}`} />
                      </button>
                      {r.icon !== r.default_icon && <span className="tag">changed</span>}
                    </td>
                    <td data-label="Name">
                      <strong>{r.name}</strong>
                    </td>
                    <td data-label="How to win it">{r.rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </>
      )}
    </div>
  );
}
