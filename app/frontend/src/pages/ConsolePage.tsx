import { useState } from "react";
import { CONSOLE_ACHIEVEMENTS_CSV, forgetResponses, getConsoleAchievements, getMe, loginUrl, runConsole } from "../api";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { GENERIC_ICON, IconEditor, IMG } from "../components/IconEditor";
import { useApi } from "../useApi";

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
  view?: "achievements";
}

const lines = (text = "") =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

/** The admin.bat menu. Who gets access is managed on the Permissions page. */
const GROUPS: { title: string; commands: Command[] }[] = [
  {
    title: "Replays",
    commands: [
      {
        name: "status",
        label: "Status and import progress",
        help: "Import progress, replay counts, failures and players.",
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
        fields: [
          {
            key: "replay",
            label: "Replay",
            hint: "Replay id or part of its file path",
          },
        ],
      },
      {
        name: "repair",
        label: "Repair a replay",
        help: "Read one damaged or incomplete replay again in repair mode, keeping every part that can be read.",
        fields: [
          {
            key: "replay",
            label: "Replay",
            hint: "Replay id or part of its file path",
          },
        ],
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
          {
            key: "unhide",
            label: "Show one again",
            hint: "File path exactly as listed",
          },
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
      {
        name: "find",
        label: "Find a player",
        help: "Search players by name or player id.",
        fields: [{ key: "term", label: "Name or id" }],
      },
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
      setResults((prev) => [
        {
          id: Date.now(),
          label: selected.label,
          ok,
          output,
          at: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
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
        The admin console on the website. Commands run on the server and changes apply straight away. Every command is logged with your
        Discord name.
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
          {selected.view === "achievements" ? (
            <AchievementExport />
          ) : (
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
