import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  findCloudPeople, getCloudLog, getCloudRule, getCloudRules, setCloudRule,
  type CloudGrant, type CloudLevel, type CloudLogEntry, type CloudPrincipal, type CloudRule, type CloudRuleRow, type DiscordEntry,
} from "../api";
import { LocalTime, Status, TableWrap } from "./common";

const who = (g: { name?: string; id: string }) => (g.name && g.name !== "?" ? g.name : g.id);
const isId = (text: string) => /^\d{17,20}$/.test(text);
const LEVEL: Record<CloudLevel, string> = { view: "View", edit: "Edit", admin: "Admin" };

/** A Discord role (from the server's list) or a person: found by name as you type, or by a pasted user id. */
export function PrincipalPicker({ roles, value, onChange, taken }: {
  roles: DiscordEntry[] | null;
  value: CloudPrincipal | null;
  onChange: (p: CloudPrincipal | null) => void;
  taken?: (type: "role" | "user", id: string) => boolean;
}) {
  const [type, setType] = useState<"role" | "user">("role");
  const [text, setText] = useState("");
  const [found, setFound] = useState<{ id: string; name: string; from: string }[] | null>(null);

  useEffect(() => { // the form was used (Add): start again
    if (!value) setText("");
  }, [value]);
  const term = text.trim();
  const searching = type === "user" && term.length >= 2 && !isId(term) && value?.name !== term;
  useEffect(() => {
    if (!searching) {
      setFound(null);
      return;
    }
    let current = true;
    const timer = setTimeout(() => { // while typing: one request when they pause
      findCloudPeople(term).then((r) => current && setFound(r.people), () => current && setFound([]));
    }, 300);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [searching, term]);

  function typed(next: string) {
    setText(next);
    const clean = next.trim();
    onChange(type === "role" || isId(clean) ? (clean ? { type, id: clean, name: "?" } : null) : null);
  }

  return (
    <>
      <select
        aria-label="A role or a person"
        value={type}
        onChange={(e) => {
          setType(e.target.value as "role" | "user");
          setText("");
          onChange(null);
        }}
      >
        <option value="role">Role</option>
        <option value="user">Person</option>
      </select>
      {type === "role" && roles ? (
        <select
          aria-label="Role"
          value={value?.type === "role" ? value.id : ""}
          onChange={(e) => {
            const role = roles.find((r) => r.id === e.target.value);
            onChange(role ? { type: "role", id: role.id, name: role.name } : null);
          }}
        >
          <option value="">Choose a role…</option>
          {roles.filter((r) => !taken?.("role", r.id)).map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      ) : (
        <span className="person-picker">
          <input
            aria-label={type === "role" ? "Role id" : "Name or Discord user id"}
            placeholder={type === "role" ? "Role id" : "Type a name, or paste a Discord user id"}
            value={text}
            onChange={(e) => typed(e.target.value)}
          />
          {value?.type === "user" && value.name !== "?" && <code>{value.id}</code>}
          {searching && found && (
            <ul className="person-found">
              {found.filter((p) => !taken?.("user", p.id)).map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setText(p.name);
                      onChange({ type: "user", id: p.id, name: p.name });
                    }}
                  >
                    {p.name}
                  </button>{" "}
                  <span className="muted">{p.from}</span> <code>{p.id}</code>
                </li>
              ))}
              {!found.length && (
                <li className="muted">Nobody found by that name. Paste their Discord user id (right-click the person &gt; Copy User ID).</li>
              )}
            </ul>
          )}
        </span>
      )}
    </>
  );
}

/** Admins of the folder (Cloud admins, console users, or listed as Admin on it or above it): who folders are shared
 *  with (View / Edit / Admin) and whether they are private. Folders only: a file follows the folder it is in. One item: its
 *  permissions, who ends up with access, and its history. Several items: one set of permissions for all of them.
 *  Nothing changes until Save; the server checks every change. */
export function CloudPermissions({ paths, onClose, onSaved }: { paths: string[]; onClose: () => void; onSaved: () => void }) {
  const path = paths[0];
  const many = paths.length > 1;
  const [rule, setRule] = useState<CloudRule | null>(null);
  const [isPrivate, setPrivate] = useState(false);
  const [grants, setGrants] = useState<CloudGrant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [adding, setAdding] = useState<CloudPrincipal | null>(null);
  const [level, setLevel] = useState<CloudLevel>("view");
  const [others, setOthers] = useState<CloudRuleRow[]>([]); // rules to copy from
  const [history, setHistory] = useState<CloudLogEntry[] | string | null>(null); // a string: why it cannot be shown
  const key = paths.join("\n");

  useEffect(() => {
    let current = true;
    setRule(null);
    setError(null);
    setSaved(false);
    setHistory(null);
    getCloudRule(path).then(
      (r) => current && (setRule(r), setPrivate(many ? false : r.private), setGrants(many ? [] : r.grants)),
      (e: Error) => current && setError(e.message),
    );
    getCloudRules().then((r) => current && setOthers(r.rules.filter((o) => many || o.path !== path)), () => {});
    return () => {
      current = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const changed = !!rule && (many ? !saved : isPrivate !== rule.private || JSON.stringify(grants) !== JSON.stringify(rule.grants));

  function add() {
    if (!adding) return;
    setGrants([...grants.filter((g) => !(g.type === adding.type && g.id === adding.id)),
      { type: adding.type, id: adding.id, level, name: adding.name }]);
    setAdding(null);
    setSaved(false);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      let now: CloudRule | null = null;
      for (const p of paths) {
        const answer = await setCloudRule(p, isPrivate, grants);
        if (p === path && "grants" in answer) now = answer;
      }
      if (now) {
        setRule(now);
        if (!many) {
          setPrivate(now.private);
          setGrants(now.grants);
        }
      }
      setSaved(true);
      setHistory(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onSaved(); // also after a failure part-way through several items: the rows show what was set
    }
  }

  function showHistory(open: boolean) {
    if (!open || history) return;
    getCloudLog(path).then(
      (rows) => setHistory(rows.filter((r) => r.path === path || r.path.startsWith(`${path}/`) || r.detail === path).slice(0, 30)),
      () => setHistory("Only console users can read the Cloud audit log (Console > Audit log)."),
    );
  }

  const what = many ? "folders" : "folder";
  return (
    <div className="panel cloud-permissions" role="dialog" aria-label={many ? `Permissions for ${paths.length} folders` : `Permissions for ${path}`}>
      <h2>Permissions: {many ? `${paths.length} folders` : path}</h2>
      {many && <p className="muted cloud-name">{paths.join(" · ")}</p>}
      {error && <p className="error">{error}</p>}
      {!rule ? (
        !error && <Status loading error={null} />
      ) : (
        <>
          <p className="muted">
            {many
              ? "Save sets the same permissions on every folder chosen, in place of the ones they have now (nothing listed and not private: their own permissions are cleared)."
              : `People with Cloud view, edit or admin on the whole cloud (Console > Permissions) reach this ${what} as usual. Here you share it with others too, or make it private.`}
            {" "}A folder's permissions apply to everything inside it, files and folders. View = download; Edit = also upload,
            new folder, rename and delete; Admin = also these permissions. Cloud admins, console users and the admins of a
            folder above always keep full access.
          </p>
          {!many && rule.above.map((a) => (
            <p key={a.path} className="muted">
              The folder <strong>{a.path}</strong> above it{" "}
              {a.private ? "is private" : "is shared"}
              {a.grants.length > 0 && `: ${a.grants.map((g) => `${who(g)} (${g.level})`).join(", ")}`}. That applies here
              too{a.private && !isPrivate ? "; people you add below get access to this one anyway" : ""}.
            </p>
          ))}
          <label className="cloud-permissions-private">
            <input
              type="checkbox"
              checked={isPrivate}
              disabled={busy}
              onChange={(e) => {
                setPrivate(e.target.checked);
                setSaved(false);
              }}
            />
            <span>
              <strong>Private</strong>: only the roles and people listed below (and admins) can see {many ? "these folders" : "this folder"}.
              Everyone else loses access, also with Cloud view or Cloud edit. Someone listed with View can only download here.
            </span>
          </label>
          <ul className="permission-list">
            {grants.map((g) => (
              <li key={`${g.type}-${g.id}`}>
                <span className="tag">{g.type === "role" ? "Role" : "Person"}</span>
                <span className="permission-name">{g.name ?? "?"}</span>
                <code>{g.id}</code>
                <select
                  aria-label={`Access for ${who(g)}`}
                  value={g.level}
                  disabled={busy}
                  onChange={(e) => {
                    setGrants(grants.map((x) => (x === g ? { ...g, level: e.target.value as CloudLevel } : x)));
                    setSaved(false);
                  }}
                >
                  <option value="view">View</option>
                  <option value="edit">Edit</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  className="link danger"
                  disabled={busy}
                  onClick={() => {
                    setGrants(grants.filter((x) => x !== g));
                    setSaved(false);
                  }}
                >
                  Remove
                </button>
              </li>
            ))}
            {!grants.length && (
              <li className="muted">{isPrivate ? "Nobody listed: only admins can see it" : "Not shared with anyone here"}</li>
            )}
          </ul>
          <form
            className="permission-add"
            onSubmit={(e) => {
              e.preventDefault();
              add();
            }}
          >
            <PrincipalPicker
              roles={rule.server_roles}
              value={adding}
              onChange={setAdding}
              taken={(type, id) => grants.some((g) => g.type === type && g.id === id)}
            />
            <select aria-label="Access" value={level} onChange={(e) => setLevel(e.target.value as CloudLevel)}>
              <option value="view">View (download)</option>
              <option value="edit">Edit (also upload, rename, delete)</option>
              <option value="admin">Admin (also sets permissions here)</option>
            </select>
            <button type="submit" className="secondary" disabled={busy || !adding}>
              Add
            </button>
          </form>
          {others.length > 0 && (
            <label className="cloud-permissions-copy">
              <span className="muted">Or copy the permissions of</span>{" "}
              <select
                aria-label="Copy the permissions of another folder"
                value=""
                disabled={busy}
                onChange={(e) => {
                  const from = others.find((o) => o.path === e.target.value);
                  if (!from) return;
                  setPrivate(from.private);
                  setGrants(from.grants);
                  setSaved(false);
                }}
              >
                <option value="">Choose a folder…</option>
                {others.map((o) => (
                  <option key={o.path} value={o.path}>
                    {o.path} ({[o.private ? "private" : "", o.grants.length ? `${o.grants.length} listed` : ""].filter(Boolean).join(", ")})
                  </option>
                ))}
              </select>
            </label>
          )}
          {!many && (
            <details className="cloud-permissions-more" open>
              <summary>Who gets in{changed ? " (as saved now, without your changes above)" : ""}</summary>
              <ul className="permission-list">
                <li>
                  <span className="tag">Console users</span>
                  <span className="permission-name">always</span>
                  <span className="tag">Admin</span>
                </li>
                {rule.effective.map((p) => (
                  <li key={`${p.type}-${p.id}`} className={p.level ? undefined : "muted"}>
                    <span className="tag">{p.type === "role" ? "Role" : "Person"}</span>
                    <span className="permission-name">{who(p)}</span>
                    <span className="tag">{p.level ? LEVEL[p.level] : "No access"}</span>
                  </li>
                ))}
              </ul>
              <p className="muted">
                Everyone with a whole-Cloud permission or named in a rule on the way here. A role stands for someone with only
                that role; a person with several gets the highest of them.
              </p>
            </details>
          )}
          {!many && (
            <details className="cloud-permissions-more" onToggle={(e) => showHistory(e.currentTarget.open)}>
              <summary>History</summary>
              {!history ? (
                <Status loading error={null} />
              ) : typeof history === "string" ? (
                <p className="muted">{history}</p>
              ) : history.length === 0 ? (
                <p className="muted">Nothing in the Cloud audit log for this {what}.</p>
              ) : (
                <ul className="cloud-permissions-history">
                  {history.map((r) => (
                    <li key={r.id} className={r.ok ? undefined : "error"}>
                      <LocalTime iso={r.at} /> · {r.who} · {r.ok ? r.action : `${r.action} refused`}
                      {r.path !== path && <span className="muted"> {r.path}</span>}
                      {r.detail && <span className="muted"> ({r.detail})</span>}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          )}
          <p className="muted">
            Someone who is logged in sees a change within 5 minutes, or at once after logging out and in again.
          </p>
        </>
      )}
      <div className="cloud-actions">
        <button disabled={busy || !changed} onClick={save}>
          {busy ? "Saving…" : many ? `Save for ${paths.length} folders` : "Save"}
        </button>
        <button className="secondary" disabled={busy} onClick={onClose}>
          {changed && !many ? "Cancel" : "Close"}
        </button>
        {saved && !changed && !error && <span className="ok-note">Saved</span>}
      </div>
    </div>
  );
}

/** Every folder / file with permissions of its own that this person is admin of, in one list (Console > Permissions,
 *  and "All permissions" on the Cloud page). */
export function CloudRulesOverview() {
  const [rows, setRows] = useState<CloudRuleRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => getCloudRules().then((r) => (setRows(r.rules), setError(null)), (e: Error) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function clear(row: CloudRuleRow) {
    if (!window.confirm(`Clear the permissions of ${row.path}?\n\n` +
      (row.exists ? "It is then open to whoever has access to the folder it is in." : "The item itself is gone; only its left-over permissions are removed."))) return;
    setBusy(true);
    try {
      await setCloudRule(row.path, false, []);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const link = (row: CloudRuleRow) => {
    const parent = row.path.split("/").slice(0, -1).join("/");
    return `/cloud?${new URLSearchParams({ ...(parent ? { path: parent } : {}), perm: row.path })}`;
  };
  return (
    <section className="cloud-rules">
      <h2>Cloud folders with their own permissions</h2>
      <p className="muted">
        Set with <strong>Permissions</strong> beside a folder on the Cloud page; files follow the folder they are in. Everything else follows the whole-cloud
        permissions (Cloud view / edit / admin in Console &gt; Permissions).
      </p>
      {error && <p className="error">{error}</p>}
      {!rows ? (
        !error && <Status loading error={null} />
      ) : rows.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr>
                <th>Folder</th>
                <th>Who</th>
                <th>Set by</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.path}>
                  <td data-label="Folder" className="cloud-name">
                    {r.private && <><span className="tag">Private</span>{" "}</>}
                    {!r.exists && <><span className="tag" title="Removed outside the site (File Station). The permissions would apply again to anything that gets this name">Item is gone</span>{" "}</>}
                    {r.exists ? <Link to={link(r)}>{r.path}</Link> : r.path}
                  </td>
                  <td data-label="Who">
                    {r.grants.length
                      ? r.grants.map((g) => `${who(g)} (${g.level})`).join(", ")
                      : <span className="muted">Admins only</span>}
                  </td>
                  <td data-label="Set by" className="nowrap">{r.by} · <LocalTime iso={r.updated_at} /></td>
                  <td>
                    <div className="cloud-row-actions">
                      {r.exists && <Link to={link(r)}>Open</Link>}
                      <button className="link danger" disabled={busy} onClick={() => clear(r)}>Clear</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </section>
  );
}
