import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import {
  type ArenaStatus, CONSOLE_ACHIEVEMENTS_CSV, CONSOLE_MEGA_PRIZES_CSV, forgetResponses, getMegaPrizeWinners, getConsoleAchievements, getConsoleLog, getConsoleOverview, getMe, getMergeSuggestions,
  getProcessingStatus, loginUrl, runConsole, searchConsolePlayers,
  type ConsoleLogEntry, type ConsoleOverview, type ConsolePlayer, type ProcessingStatus,
} from "../api";
import { SplitBar } from "../components/bars";
import { PlayerSuggest } from "../components/PlayerSuggest";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { dateTime, duration, int, num, pct, playerPath } from "../format";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { Permissions } from "./PermissionsPage";
import { GENERIC_ICON, IconEditor, IMG } from "../components/IconEditor";
import { useApi, useWhileVisible } from "../useApi";
import { usePageTitle } from "../usePageTitle";

type Field = {
  key: string;
  label: string;
  kind?: "text" | "date" | "check" | "list" | "select" | "player" | "players"; // player(s): suggests players while typing (one / one per line)
  hint?: string;
  options?: [value: string, label: string][]; // select
};

interface Command {
  name: string; // the admin.bat command the server runs
  label: string;
  help: string;
  fields?: Field[];
  /** asked before running, like the console's "[y/N]" */
  confirm?: (values: Record<string, string>) => string | null;
  /** a page of its own instead of a command form */
  view?: "achievements" | "winners" | "dashboard" | "players" | "hidden-stats" | "log" | "processing" | "permissions";
  /** big or hard to undo: shown apart, in the tab's danger area */
  danger?: boolean;
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
      { name: "hidden-stats", label: "Hide stats from players", help: "", view: "hidden-stats" },
      { name: "permissions", label: "Permissions", help: "", view: "permissions" },
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
          { key: "main", label: "Player to keep", kind: "player", hint: "Start typing a name or id" },
          {
            key: "others",
            label: "Records to merge into it",
            kind: "players",
            hint: "One name or id per line; start typing to find a player",
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
        name: "link-profile",
        label: "Link a player to a Discord account",
        help: "When a player cannot be verified automatically: that Discord account can then log in and edit the bio on the player's page. Relinking moves the link.",
        fields: [
          { key: "player", label: "Player", kind: "player", hint: "Start typing a name or id" },
          { key: "discord_id", label: "Discord user id", hint: "In Discord: right-click the person > Copy User ID" },
        ],
        confirm: (v) => `Link ${v.player} to Discord account ${v.discord_id}?`,
      },
      {
        name: "unlink-profile",
        label: "Remove a Discord link",
        help: "The bio goes with the link.",
        fields: [{ key: "player", label: "Player or Discord id", hint: "A name, player id or Discord id" }],
        confirm: (v) => `Remove the Discord link of ${v.player}?`,
      },
      { name: "profile-links", label: "Discord link report", help: "How many players are linked to a Discord account, and how." },
      {
        name: "unmerge",
        label: "Undo a merge",
        help: "Make a merged record a separate player again.",
        fields: [{ key: "alias", label: "Merged id", hint: "From “List merges”" }],
        confirm: (v) => `Undo the merge of ${v.alias}?`,
      },

      {
        name: "discord-check",
        label: "Check a member's access",
        help: "Whether one person is an Admin, gets the Preview and the Console page. To change who gets what, use the Permissions page.",
        fields: [{ key: "user_id", label: "Discord user id", hint: "In Discord: right-click the person > Copy User ID" }],
      },
    ],
  },
  {
    title: "Processing",
    commands: [
      { name: "status", label: "Status and import progress", help: "", view: "processing" },
      {
        name: "remote",
        label: "Where replays are processed",
        help:
          "Who reads the replays: this server, another PC (remote_worker.bat) or both at once, each taking different replays from " +
          "the queue. With the PC only, the NAS stays free for visitors and nothing is processed until the PC is running. Leave it on " +
          "“just show” to see the current setting and when the PC last asked for work.",
        fields: [
          {
            key: "mode",
            label: "Process on",
            kind: "select",
            options: [
              ["", "Just show the current setting"],
              ["server", "This server only"],
              ["remote", "Another PC only"],
              ["both", "Both the PC and this server"],
            ],
          },
        ],
        confirm: (v) =>
          v.mode === "remote"
            ? "Stop this server from reading replays and leave it to the other PC?"
            : v.mode === "both"
              ? "Let both this server and the PC read replays?"
              : v.mode === "server"
                ? "Let this server read replays itself again? What the PC still holds is queued again."
                : null,
      },
      {
        name: "process-missing",
        label: "Process missing replay files",
        help: "Scan the replay folder, then queue every file that has no match yet: new files, replays that finished without a match and ones that could not be read earlier. Nothing is queued twice, so it is safe to run again.",
      },
      {
        name: "reprocess-all",
        label: "Re-process every replay",
        help: "Scan the folder, then read the whole archive again. This takes hours; current results stay on the website until each replay is replaced.",
        confirm: () => "Re-process EVERY replay? This takes several hours.",
        danger: true,
      },
    ],
  },
  {
    title: "Repair",
    commands: [
      {
        name: "fix-replay", // the form of reprocess, repair and repair-aggressive: Strength picks which one runs (see submit)
        label: "Fix a replay",
        help:
          "Read one replay again. Normal is enough after an update. Repair keeps every part of a damaged or incomplete replay that can be read. " +
          "Aggressive is for broken replay data that repair could not fix: it rebuilds wiped zip headers and takes damaged parts from the zip's second copy of the frames. Nothing is guessed.",
        fields: [
          { key: "replay", label: "Replay", hint: "Replay id or part of its file path" },
          {
            key: "strength",
            label: "Strength",
            kind: "select",
            options: [
              ["", "Normal: read it again"],
              ["repair", "Repair: keep what can be read"],
              ["repair-aggressive", "Aggressive: rebuild broken data"],
            ],
          },
        ],
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
      { name: "mega-prizes", label: "Mega Prize winners", help: "", view: "winners" },
      {
        name: "mega-period",
        label: "Mega Prize period",
        help:
          "The Start and End dates for the Mega Prizes, apart from the achievements' dates above. Only Echo Combat matches and Public Arena matches inside them count towards a prize. " +
          "With no start date of its own the Mega Prize period follows the launch date and challenge period, so nothing changes until you set one. " +
          "“Visible to” decides who sees the Mega Prizes: only people with the Preview role (how it started), everyone once the start date has come, or nobody. " +
          "Leave everything empty to see the current setting; an empty date is kept as it is.",
        fields: [
          { key: "start", label: "Start", kind: "date" },
          { key: "start_today", label: "Start today", kind: "check" },
          { key: "end", label: "End (optional)", kind: "date" },
          { key: "end_today", label: "End today", kind: "check" },
          { key: "clear", label: "Remove both dates (follow the challenge period)", kind: "check" },
          {
            key: "visible",
            label: "Visible to",
            kind: "select",
            options: [
              ["", "Keep as it is"],
              ["everyone", "Everyone, from the start date on"],
              ["preview", "Only people with the Preview role"],
              ["hidden", "Nobody (hide it, Preview included)"],
            ],
          },
        ],
        confirm: (v) =>
          v.visible === "hidden"
            ? "Hide the Mega Prizes from everyone, people with the Preview role included?"
            : v.visible === "everyone"
              ? "Show the Mega Prizes to everyone from the Mega Prize start date on?"
              : v.visible === "preview"
                ? "Show the Mega Prizes only to people with the Preview role?"
                : v.clear
            ? "Remove the Mega Prize dates? The prizes follow the challenge period again."
            : v.start_today
              ? `Start the Mega Prize period today (${todayIso()})? Matches before today stop counting for the prizes.`
              : v.start
                ? `Set the Mega Prize start date to ${v.start}? Matches before it stop counting for the prizes.`
                : v.end_today
                  ? `End the Mega Prize period today (${todayIso()})?`
                  : v.end
                    ? `Set the Mega Prize end date to ${v.end}?`
                    : null,
      },
      {
        name: "challenge",
        label: "Launch date and challenge period",
        help:
          "The start date is the launch: until then achievements and challenges show “Coming soon”, and only matches from that day count. " +
          "“Visible to” decides who sees them: everyone once the start date has come, only people with the Preview role (the date still counts), or nobody. " +
          "These dates only affect achievements, challenges and Mega Prizes: the games, wins and other numbers on the general player stats pages always count every match. " +
          "Leave everything empty to see the current setting; an empty date is kept as it is.",
        fields: [
          { key: "start", label: "Start", kind: "date" },
          { key: "start_today", label: "Start today (launches now)", kind: "check" },
          { key: "end", label: "End (optional)", kind: "date" },
          { key: "end_today", label: "End today", kind: "check" },
          { key: "clear", label: "Remove both dates", kind: "check" },
          {
            key: "visible",
            label: "Visible to",
            kind: "select",
            options: [
              ["", "Keep as it is"],
              ["everyone", "Everyone, from the start date on"],
              ["preview", "Only people with the Preview role"],
              ["hidden", "Nobody (hide it, Preview included)"],
            ],
          },
        ],
        confirm: (v) =>
          v.visible === "hidden"
            ? "Hide achievements and challenges from everyone, people with the Preview role included?"
            : v.visible === "everyone" && !v.start && !v.start_today
              ? "Make achievements visible to everyone from the start date that is already set?"
              : v.visible === "preview"
                ? "Show achievements only to people with the Preview role?"
                : v.clear
                  ? "Remove both dates? Achievements go back to “Coming soon”."
            : v.start_today
              ? `Launch now: set the start date to today (${todayIso()})? Achievements become public.`
              : v.start
                ? `Set the launch date to ${v.start}?`
                : v.end_today
                  ? `End the challenge period today (${todayIso()})?`
                  : null,
      },
    ],
  },
];

const ALL_COMMANDS = GROUPS.flatMap((g) => g.commands);
const commandNamed = (name: string) => ALL_COMMANDS.find((c) => c.name === name)!;

/** The Console's tabs. `names`: its commands as buttons, first = what the tab opens with. `opens` false: the tab opens on its
 * status panel, with no action chosen (user, 2026-11-05: status first, then actions, the risky ones apart). */
const TABS: { id: string; label: string; names: string[]; opens?: false }[] = [
  { id: "dashboard", label: "Dashboard", names: ["dashboard"] },
  { id: "players", label: "Players", names: ["players", "merge", "merges", "unmerge", "discord-check"] },
  {
    id: "replays",
    label: "Replays",
    opens: false,
    names: ["remote", "process-missing", "fix-replay", "repair-failed", "repair-aggressive-failed", "cannot-repair", "hidden", "reprocess-all"],
  },
  // starts on the dates: the winners report reads the whole archive, which takes up to half a minute during a re-read
  { id: "achievements", label: "Achievements", names: ["challenge", "mega-period", "mega-prizes", "hidden-stats", "export-achievements"] },
  { id: "log", label: "Audit log", names: ["log"] },
  { id: "permissions", label: "Permissions", names: ["permissions"] },
];

/** The menu label of a command, for the audit log; commands run from a view (hide-stats) get a name of their own. */
const COMMAND_LABELS: Record<string, string> = {
  ...Object.fromEntries(ALL_COMMANDS.map((c) => [c.name, c.label])),
  "hide-stats": "Hide stats from players",
  find: "Find a player",
  "remote-status": "Where replays are processed",
  "remote-on": "Process replays on another PC",
  "remote-off": "Process replays on this server again",
  "preview-roles": "Discord preview roles",
  "admin-roles": "Discord admin roles",
  "admin-users": "Discord admin users",
};

/** Today as YYYY-MM-DD in this browser's calendar (the Start today / End today options). */
function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** What the server expects: text, true / false, and `others` as a list. An empty date is left out (= keep). The
 *  "… today" checks fill the start / end date; the server still checks the person's permission for the command. */
function toArgs(fields: Field[], values: Record<string, string>): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.key === "start_today" || f.key === "end_today") continue;
    const v = values[f.key] ?? "";
    if (f.kind === "check") args[f.key] = v === "1";
    else if (f.kind === "list" || f.kind === "players") args[f.key] = lines(v);
    else if (f.kind !== "date" || v) args[f.key] = v.trim();
  }
  if (values.start_today === "1") args.start = todayIso();
  if (values.end_today === "1") args.end = todayIso();
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
  usePageTitle("Console");
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
  // in the address (?tab=replays&cmd=fix-replay): a refresh keeps the place, and it can be linked to
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.id === params.get("tab")) ?? TABS[0];
  const cmd = params.get("cmd");
  const selected: Command | null = cmd && tab.names.includes(cmd) ? commandNamed(cmd) : tab.opens === false ? null : commandNamed(tab.names[0]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[]>([]);
  const [filter, setFilter] = useState("");
  const touched = useRef(new Set<string>()); // fields typed or picked since the form was opened / last saved
  const set = (key: string, value: string) => {
    touched.current.add(key);
    setValues((v) => ({ ...v, [key]: value }));
  };

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

  function openTab(id: string) {
    setParams(id === TABS[0].id ? {} : { tab: id });
    setValues({});
  }

  function open(name: string, preset: Record<string, string> = {}) {
    const target = TABS.find((t) => t.names.includes(name));
    if (!target) return;
    setParams(target.id === TABS[0].id ? {} : { tab: target.id, cmd: name });
    setValues(preset);
    setFilter("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submit() {
    if (!selected) return;
    const question = selected.confirm?.(values);
    if (question && !window.confirm(question)) return;
    if (selected.name === "fix-replay") {
      const name = values.strength || "reprocess"; // three commands on the server, one form here
      await execute(name, COMMAND_LABELS[name], toArgs((selected.fields ?? []).filter((f) => f.key !== "strength"), values));
      return;
    }
    await execute(selected.name, selected.label, toArgs(selected.fields ?? [], values));
  }

  // The launch date, end date and "Visible to" are saved on the server (they survive closing the Console and restarts): the form
  // shows what is saved instead of opening empty (user, 2026-11-04). It is read when the form opens and again after a command that
  // WORKED. What the person has typed or picked is never overwritten by a late answer (the server can be slow), and a refused save
  // keeps their input so they can correct it (user, 2026-11-06: the dates kept resetting to dd/mm/yyyy).
  const ran = useRef(results.length);
  useEffect(() => {
    const afterCommand = results.length !== ran.current;
    ran.current = results.length;
    if (!afterCommand) touched.current = new Set(); // a different form
    if (selected?.name !== "challenge" && selected?.name !== "mega-period") return;
    if (afterCommand && !results[0]?.ok) return; // refused: keep what was typed
    const mega = selected.name === "mega-period";
    const reset = afterCommand; // after a successful save the form shows exactly what the server now holds
    if (reset) touched.current = new Set();
    let live = true;
    getConsoleOverview().then((o) => {
      if (!live) return;
      const saved: Record<string, string> = mega
        ? { start: o.mega_period.start ?? "", end: o.mega_period.end ?? "", visible: o.mega_period.visibility }
        : { start: o.challenge.start ?? "", end: o.challenge.end ?? "", visible: o.challenge.visibility };
      setValues((v) => {
        const mine = Object.fromEntries(Object.entries(v).filter(([k]) => touched.current.has(k)));
        return { ...saved, ...mine };
      });
    }, () => undefined);
    return () => {
      live = false;
    };
  }, [selected, results.length]);

  const api: ConsoleApi = { run: execute, open, version: results.length };
  const term = filter.trim().toLowerCase();
  const found = term
    ? TABS.flatMap((t) => t.names.map((name) => ({ tab: t, command: commandNamed(name) }))).filter(({ tab: t, command: c }) =>
        `${t.label} ${c.label} ${c.help}`.toLowerCase().includes(term),
      )
    : [];
  const commands = tab.names.map(commandNamed);
  const actionButton = (c: Command) => (
    <button
      key={c.name}
      type="button"
      className={c === selected ? "active" : "secondary"}
      aria-current={c === selected}
      onClick={() => open(c.name)}
    >
      {c.label}
    </button>
  );

  return (
    <section>
      <div className="console-title">
        <h1>Console</h1>
        <p className="muted">
          Commands run on the server and apply straight away. Every command is written to the audit log with your Discord name.
        </p>
      </div>
      <div className="console-bar">
        <div className="tabs section-tabs console-tabs" role="tablist" aria-label="Console">
          {TABS.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={t === tab} className={t === tab ? "tab active" : "tab"} onClick={() => openTab(t.id)}>
              <span className="tab-label">{t.label}</span>
            </button>
          ))}
        </div>
        <div className="console-find">
          <input
            type="search"
            className="console-filter"
            placeholder="Find a command"
            aria-label="Find a command"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {term && (
            <div className="panel console-found">
              {found.map(({ tab: t, command: c }) => (
                <button key={c.name} type="button" className="secondary" onClick={() => open(c.name)}>
                  <span className="muted">{t.label} ›</span> {c.label}
                </button>
              ))}
              {found.length === 0 && <p className="muted">No command matches.</p>}
            </div>
          )}
        </div>
      </div>
      <div className="console-main">
        {tab.id === "replays" && <ReplaysStatus />}
        {commands.length > 1 && (
          <div className="console-actions" aria-label="Actions">
            {commands.filter((c) => !c.danger).map(actionButton)}
          </div>
        )}
        {selected &&
          (selected.view === "dashboard" ? (
            <Dashboard api={api} />
          ) : selected.view === "players" ? (
            <PlayerTools api={api} />
          ) : selected.view === "hidden-stats" ? (
            <HiddenStats api={api} />
          ) : selected.view === "log" ? (
            <AuditLog api={api} />
          ) : selected.view === "achievements" ? (
            <AchievementExport />
          ) : selected.view === "winners" ? (
            <MegaPrizeReport />
          ) : selected.view === "permissions" ? (
            <Permissions />
          ) : selected.view === "processing" ? (
            <ProcessingPanel />
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
                    {f.kind === "select" ? (
                      <select value={values[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)}>
                        {f.options?.map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    ) : f.kind === "player" || f.kind === "players" ? (
                      <PlayerSuggest
                        multiline={f.kind === "players"}
                        placeholder={f.hint}
                        value={values[f.key] ?? ""}
                        onChange={(v) => set(f.key, v)}
                        search={searchConsolePlayers}
                      />
                    ) : f.kind === "list" ? (
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
          ))}
        {selected?.name === "merge" && (
          <MergeSuggestions
            version={results.length}
            onUse={(keep, others) => {
              setValues({ main: keep, others: others.join("\n") });
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        )}
        {commands.some((c) => c.danger) && (
          <div className="panel console-danger">
            <h3>Danger area</h3>
            <p className="muted">These take hours or touch every replay. Each one asks you to confirm before it runs.</p>
            <div className="console-actions">{commands.filter((c) => c.danger).map(actionButton)}</div>
          </div>
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

/** The import in one panel: how far, how fast, how long. */
function ImportProgress({ status }: { status: ProcessingStatus }) {
  const c = status.counts;
  const total = c.queued + c.processing + c.done + c.failed;
  const finished = c.done + c.failed;
  const waiting = c.queued + c.processing;
  return (
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
  );
}

/** Top of the Replays tab: short, so the actions stay in view; the long status page opens on request. */
function ReplaysStatus() {
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  useWhileVisible(
    () =>
      getProcessingStatus().then(
        (s) => {
          setStatus(s);
          setError(null);
        },
        (e: Error) => setError(e.message),
      ),
    10_000,
  );
  return (
    <>
      {status ? <ImportProgress status={status} /> : <Status loading={!error} error={error} />}
      <div>
        <button type="button" className="secondary small" aria-expanded={full} onClick={() => setFull((v) => !v)}>
          {full ? "Hide full status" : "Show full status"}
        </button>
      </div>
      {full && <ProcessingPanel />}
    </>
  );
}

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
  const winLoss = overview.stat_groups.find((g) => g.key === "win_loss");
  const scan = status.scan;

  return (
    <div className="console-view">
      <div className="section-head">
        <h2>Dashboard</h2>
        <span className="muted">{error ? `Could not refresh: ${error}` : at && `Updated ${at.toLocaleTimeString()} · every 10 s`}</span>
      </div>

      <ImportProgress status={status} />

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
        <DashCard
          label="Achievements"
          value={overview.challenge.launched ? "Live" : overview.challenge.visibility === "hidden" ? "Hidden" : overview.challenge.visibility === "preview" ? "Preview only" : "Coming soon"}
        >
          {overview.challenge.start ? `From ${overview.challenge.start}${overview.challenge.end ? ` to ${overview.challenge.end}` : ""}` : "No launch date set"}
          <button type="button" className="secondary small" onClick={() => api.open("challenge")}>Change</button>
        </DashCard>
        <DashCard label="Mega Prizes" value={overview.mega_period.start ? "Own dates" : "Follows challenge"}>
          {overview.mega_period.start
            ? `From ${overview.mega_period.start}${overview.mega_period.end ? ` to ${overview.mega_period.end}` : ""}`
            : overview.challenge.start
              ? `From ${overview.challenge.start}${overview.challenge.end ? ` to ${overview.challenge.end}` : ""}`
              : "No start date set"}
          <button type="button" className="secondary small" onClick={() => api.open("mega-period")}>Change</button>
        </DashCard>
        <ArenaCard status={overview.arena_status} />
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

const ARENA_STATES: Record<ArenaStatus["state"], [value: string, detail: string]> = {
  off: ["Off", "Not running on this server"],
  outside_period: ["Waiting", "Outside the Mega Prize period: the match list is not being read"],
  waiting: ["Starting", "No answer from the match list yet"],
  working: ["Working", ""],
  failing: ["Failing", "The match list has not answered lately"],
};

const clock = (iso?: string | null) => (iso ? new Date(iso).toLocaleTimeString() : "");

/** Is the Public Arena counter alive? From the server's memory, so it needs no wait and no request to the match list. */
function ArenaCard({ status: s }: { status: ArenaStatus }) {
  const [value, detail] = ARENA_STATES[s.state];
  return (
    <DashCard label="Arena counter" value={value} bad={s.state === "failing"}>
      {detail}
      {detail && s.last_ok_at && " · "}
      {s.last_ok_at && `Read ${clock(s.last_ok_at)}: ${int(s.matches_now ?? 0)} public matches, ${int(s.players_now ?? 0)} players`}
      {s.state !== "off" && ` · ${int(s.counted_since_start ?? 0)} counted since the restart`}
      {s.last_counted_at && `, the last at ${clock(s.last_counted_at)}`}
      {s.last_error && <span className="error-text"> · Last error {clock(s.last_error_at)}: {s.last_error}</span>}
    </DashCard>
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
              {int(p.games)} games · seen {dateTime(p.first_seen_at).slice(0, 10)} – {dateTime(p.last_seen_at).slice(0, 10)}
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
                        {dateTime(p.first_seen_at).slice(0, 10)} – {dateTime(p.last_seen_at).slice(0, 10)}
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

/** Mega Prize winners report (prizes are given out by hand): who reached each target inside the Mega Prize period. */
function MegaPrizeReport() {
  const [run, setRun] = useState(0); // Refresh asks again
  const report = useApi(getMegaPrizeWinners, `console-mega-prizes-${run}`);
  const [copied, setCopied] = useState(false);
  const d = report.data;

  async function copy() {
    const rows = d!.prizes.flatMap((p) => p.winners.map((w) => [p.prize, w.name, w.user_id, w.discord_id ?? "", w.count].join("\t")));
    await navigator.clipboard.writeText(["Prize\tName\tPlayer id\tDiscord id\tMatches", ...rows].join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="panel console-form">
      <h2>Mega Prize winners</h2>
      <p className="muted">
        Everyone who has reached a Mega Prize target inside the Mega Prize period
        {d ? ` (${d.period.start ?? "no start date set"} to ${d.period.end ?? "open-ended"})` : ""}. Combat counts the replay files; Public Arena counts
        matches of 4+ minutes from the live match list.
      </p>
      <div className="filters">
        <button className="secondary" type="button" onClick={() => setRun((n) => n + 1)}>
          Refresh
        </button>
        <button className="secondary" type="button" disabled={!d?.prizes.some((p) => p.winners.length)} onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <a className="button" href={CONSOLE_MEGA_PRIZES_CSV} download>
          Download CSV
        </a>
      </div>
      <Status loading={report.loading} error={report.error} />
      {d &&
        d.prizes.map((p) => (
          <div key={p.prize}>
            <h3>
              {p.prize}{" "}
              <span className="muted">
                · {p.challenge} · {p.winners.length} winner{p.winners.length === 1 ? "" : "s"}
              </span>
            </h3>
            {p.winners.length > 0 && (
              <TableWrap>
                <table className="stack">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Player id</th>
                      <th>Discord id</th>
                      <th>Matches</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.winners.map((w) => (
                      <tr key={w.user_id}>
                        <td data-label="Name">
                          <strong>{w.name}</strong>
                        </td>
                        <td data-label="Player id">{w.user_id}</td>
                        <td data-label="Discord id">{w.discord_id ?? "not linked"}</td>
                        <td data-label="Matches">{w.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </div>
        ))}
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
