import { useState } from "react";
import { forgetResponses, getMe, loginUrl, runConsole } from "../api";
import { Status } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";

type Field = { key: string; label: string; kind?: "text" | "date" | "check" | "list"; placeholder?: string };

interface Command {
  name: string; // as in admin.bat
  label: string;
  help: string;
  fields?: Field[];
  /** asked before running; the console's own "[y/N]" */
  confirm?: (args: Record<string, string>) => string | null;
}

/** The admin.bat menu, same order and numbers. Options 14, 15 and 17 only show who has access here: changing it
 * stays in admin.bat. */
const GROUPS: { title: string; commands: Command[] }[] = [
  {
    title: "Players",
    commands: [
      { name: "find", label: "1 Find a player", help: "Players by name or id.", fields: [{ key: "term", label: "Name or id" }] },
      {
        name: "merge",
        label: "2 Merge player records",
        help: "For one person who appears under several player ids. Names must match one player; use the id otherwise.",
        fields: [
          { key: "main", label: "Player to keep (name or id)" },
          { key: "others", label: "Records to merge into it (one per line)", kind: "list" },
        ],
        confirm: (a) => `Merge ${a.others.split("\n").filter((o) => o.trim()).length} record(s) into ${a.main}? Their replays are re-processed.`,
      },
      { name: "merges", label: "3 List merges", help: "Every merge, newest first." },
      {
        name: "unmerge",
        label: "4 Undo a merge",
        help: "The merged id from List merges (or a unique name).",
        fields: [{ key: "alias", label: "Merged id" }],
        confirm: (a) => `Undo the merge of ${a.alias}?`,
      },
    ],
  },
  {
    title: "Achievements",
    commands: [
      {
        name: "challenge",
        label: "5 Launch / Flamingo Challenge period",
        help:
          'Start = launch date: achievements and challenges are "Coming soon" until then and only count matches from it. ' +
          "Leave a date empty to keep it; tick Clear to remove both. Run with both empty to see the current period.",
        fields: [
          { key: "start", label: "Start", kind: "date" },
          { key: "end", label: "End", kind: "date" },
          { key: "clear", label: "Clear both dates", kind: "check" },
        ],
        confirm: (a) => (a.clear ? "Remove both dates? Achievements go back to \"Coming soon\"." : null),
      },
    ],
  },
  {
    title: "Replays",
    commands: [
      { name: "status", label: "6 Status and import progress", help: "Server, import progress, failures, players." },
      {
        name: "repair-failed",
        label: "7 Repair failed replays",
        help: "Re-process damaged / incomplete replays in repair (salvage) mode, one attempt each.",
        confirm: () => "Re-process every damaged / incomplete replay in repair mode?",
      },
      {
        name: "cannot-repair",
        label: "8 Replays that cannot be repaired",
        help: "Lists them. Tick Hide to leave them out of the failed lists and counts (nothing is deleted).",
        fields: [{ key: "hide", label: "Hide them", kind: "check" }],
        confirm: (a) => (a.hide ? "Hide every failed replay that cannot be repaired?" : null),
      },
      {
        name: "hidden",
        label: "9 Hidden replays",
        help: "Lists hidden replays. To show one again, enter its path exactly as listed, or tick Show all.",
        fields: [
          { key: "unhide", label: "Path to show again" },
          { key: "unhide_all", label: "Show all again", kind: "check" },
        ],
        confirm: (a) => (a.unhide_all ? "Show every hidden replay on the website again?" : a.unhide ? `Show ${a.unhide} again?` : null),
      },
      { name: "reprocess", label: "10 Re-process a replay", help: "Read one replay again.", fields: [{ key: "replay", label: "Replay id or file path" }] },
      {
        name: "repair",
        label: "11 Repair a replay",
        help: "Re-process one damaged replay in repair mode.",
        fields: [{ key: "replay", label: "Replay id or file path" }],
      },
      { name: "scan", label: "12 Scan the replay folder now", help: "Look for new / changed files (the server also does this every few minutes)." },
      {
        name: "reprocess-all",
        label: "13 Rescan and re-process every replay",
        help: "Reads the whole archive again: hours. Current results stay on the website until each replay is replaced.",
        confirm: () => "Rescan and re-process EVERY replay? This takes hours.",
      },
    ],
  },
  {
    title: "Discord access",
    commands: [
      { name: "preview-roles", label: "14 Preview roles", help: "Roles that see achievements before the launch. Change them in admin.bat (option 14)." },
      { name: "admin-roles", label: "15 Admin roles", help: "Roles that get the Admin tab. Change them in admin.bat (option 15)." },
      {
        name: "discord-check",
        label: "16 Check a Discord member's access",
        help: "What the website sees for one person (right-click them in Discord > Copy User ID).",
        fields: [{ key: "user_id", label: "Discord user id" }],
      },
      { name: "admin-users", label: "17 Admin users", help: "People who are admins by user id. Change them in admin.bat (option 17)." },
    ],
  },
];

/** What the server expects: strings, booleans, and `others` as a list. Empty dates are left out (= keep). */
function toArgs(fields: Field[], values: Record<string, string>): Record<string, unknown> {
  const args: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key] ?? "";
    if (f.kind === "check") args[f.key] = v === "1";
    else if (f.kind === "list") args[f.key] = v.split("\n").map((s) => s.trim()).filter(Boolean);
    else if (f.kind === "date") {
      if (v) args[f.key] = v;
    } else args[f.key] = v;
  }
  return args;
}

interface Run {
  id: number;
  label: string;
  ok: boolean;
  output: string;
  at: string;
}

/** admin.bat on the website (D45), for Discord members with a role from ECHOVR_DISCORD_PREVIEW_ROLES. */
export function ConsolePage() {
  const me = useApi(getMe, "me");
  if (!me.data) return <Status loading={me.loading} error={me.error} />;
  const user = me.data.user;
  if (!user?.console)
    return (
      <section>
        <h1>Console</h1>
        <EmptyState title="Not available">
          {!me.data.enabled ? (
            "Discord login is not set up on this server."
          ) : user ? (
            <>Logged in as {user.name}, but your Discord account does not have a console role.</>
          ) : (
            <a href={loginUrl("/console")}>Log in with Discord</a>
          )}
        </EmptyState>
      </section>
    );
  return <Console />;
}

function Console() {
  const [selected, setSelected] = useState<Command>(GROUPS[2].commands[0]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);

  function pick(c: Command) {
    setSelected(c);
    setValues({});
  }

  async function run() {
    const question = selected.confirm?.({ ...values, others: values.others ?? "" });
    if (question && !window.confirm(question)) return;
    setBusy(true);
    const at = new Date().toLocaleTimeString();
    try {
      const r = await runConsole(selected.name, toArgs(selected.fields ?? [], values));
      setRuns((prev) => [{ id: Date.now(), label: selected.label, ok: r.ok, output: r.output || "(no output)", at }, ...prev]);
      forgetResponses(); // the website shows the change straight away
    } catch (e) {
      setRuns((prev) => [{ id: Date.now(), label: selected.label, ok: false, output: (e as Error).message, at }, ...prev]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Console</h1>
      <p className="muted">
        The admin console (admin.bat) on the website: the same commands, run on the server. Changes apply straight away, like in admin.bat.
      </p>
      <div className="console-layout">
        <nav className="console-menu" aria-label="Console commands">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <h2>{g.title}</h2>
              {g.commands.map((c) => (
                <button key={c.name} className={c === selected ? "active" : "secondary"} onClick={() => pick(c)}>
                  {c.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div>
          <form
            className="panel"
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
          >
            <h2>{selected.label}</h2>
            <p className="muted">{selected.help}</p>
            {selected.fields && (
              <div className="filters">
                {selected.fields.map((f) =>
                  f.kind === "check" ? (
                    <label key={f.key} className="check">
                      <input
                        type="checkbox"
                        checked={values[f.key] === "1"}
                        onChange={(e) => setValues({ ...values, [f.key]: e.target.checked ? "1" : "" })}
                      />{" "}
                      {f.label}
                    </label>
                  ) : (
                    <label key={f.key}>
                      {f.label}
                      {f.kind === "list" ? (
                        <textarea rows={3} value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                      ) : (
                        <input
                          type={f.kind === "date" ? "date" : "text"}
                          value={values[f.key] ?? ""}
                          onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                        />
                      )}
                    </label>
                  ),
                )}
              </div>
            )}
            <button type="submit" disabled={busy}>
              {busy ? "Running…" : "Run"}
            </button>
          </form>
          {runs.map((r) => (
            <div key={r.id} className="panel console-output">
              <div className="section-head">
                <strong className={r.ok ? undefined : "error"}>{r.label}</strong>
                <span className="muted">{r.at}</span>
              </div>
              <pre>{r.output}</pre>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
