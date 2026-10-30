import { useState } from "react";
import { forgetResponses, getMe, loginUrl, runConsole } from "../api";
import { Status } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";

type Field = { key: string; label: string; kind?: "text" | "date" | "check" | "list"; hint?: string };

interface Command {
  name: string; // the admin.bat command the server runs
  label: string;
  help: string;
  fields?: Field[];
  /** asked before running, like the console's "[y/N]" */
  confirm?: (values: Record<string, string>) => string | null;
}

const lines = (text = "") => text.split("\n").map((s) => s.trim()).filter(Boolean);

/** The admin.bat menu. Who gets the preview / Admin tab is only shown here: changing it stays in admin.bat. */
const GROUPS: { title: string; commands: Command[] }[] = [
  {
    title: "Replays",
    commands: [
      { name: "status", label: "Status and import progress", help: "Import progress, replay counts, failures and players." },
      { name: "scan", label: "Scan the replay folder", help: "Look for new and changed replay files now. The server also does this every few minutes." },
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
    title: "Players",
    commands: [
      { name: "find", label: "Find a player", help: "Search players by name or player id.", fields: [{ key: "term", label: "Name or id" }] },
      {
        name: "merge",
        label: "Merge player records",
        help: "For one person who appears under several player ids. Their replays are read again, so the merge can always be undone.",
        fields: [
          { key: "main", label: "Player to keep", hint: "Name or id" },
          { key: "others", label: "Records to merge into it", kind: "list", hint: "One name or id per line" },
        ],
        confirm: (v) => `Merge ${lines(v.others).length} record(s) into ${v.main}?`,
      },
      { name: "merges", label: "List merges", help: "Every merge, newest first." },
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
    title: "Achievements",
    commands: [
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
    title: "Discord access (view only)",
    commands: [
      {
        name: "discord-check",
        label: "Check a member's access",
        help: "Whether one person gets the Admin tab, the Preview and the Console page.",
        fields: [{ key: "user_id", label: "Discord user id", hint: "In Discord: right-click the person > Copy User ID" }],
      },
      { name: "preview-roles", label: "Preview roles", help: "Roles that see achievements before the launch. To change them, use admin.bat (option 14)." },
      { name: "admin-roles", label: "Admin roles", help: "Roles that get the Admin tab. To change them, use admin.bat (option 15)." },
      { name: "admin-users", label: "Admin users", help: "People who get the Admin tab by their user id. To change them, use admin.bat (option 17)." },
    ],
  },
];

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
  const set = (key: string, value: string) => setValues((v) => ({ ...v, [key]: value }));

  async function run() {
    const question = selected.confirm?.(values);
    if (question && !window.confirm(question)) return;
    setBusy(true);
    const add = (ok: boolean, output: string) =>
      setResults((prev) => [{ id: Date.now(), label: selected.label, ok, output, at: new Date().toLocaleTimeString() }, ...prev]);
    try {
      const r = await runConsole(selected.name, toArgs(selected.fields ?? [], values));
      add(r.ok, r.output || "Done.");
      forgetResponses(); // other pages show the change straight away
    } catch (e) {
      add(false, (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Console</h1>
      <p className="muted">
        The admin console on the website. Commands run on the server and changes apply straight away. Every command is logged with your Discord
        name.
      </p>
      <div className="console-layout">
        <nav className="console-menu" aria-label="Console commands">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <h2>{g.title}</h2>
              {g.commands.map((c) => (
                <button
                  key={c.name}
                  className={c === selected ? "active" : "secondary"}
                  aria-current={c === selected}
                  onClick={() => {
                    setSelected(c);
                    setValues({});
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="console-main">
          <form
            className="panel console-form"
            onSubmit={(e) => {
              e.preventDefault();
              run();
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
          {results.length > 0 && (
            <div className="section-head">
              <h2>Results</h2>
              <button className="secondary" onClick={() => setResults([])}>
                Clear
              </button>
            </div>
          )}
          {results.map((r) => (
            <article key={r.id} className={`panel console-output${r.ok ? "" : " failed"}`}>
              <header>
                <strong>{r.label}</strong>
                <span className={r.ok ? "tag" : "tag error"}>{r.ok ? "Done" : "Failed"}</span>
                <span className="muted">{r.at}</span>
              </header>
              <pre>{r.output}</pre>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
