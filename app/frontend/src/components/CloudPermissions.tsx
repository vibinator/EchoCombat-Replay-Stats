import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  changeCloudAccess, findCloudPeople, getCloudAccess, getCloudEffective, getCloudLog, getCloudRule, getCloudRules, setCloudRule,
  type CloudAccessState, type CloudEffective, type CloudGrant, type CloudLevel, type CloudPermission, type CloudLogEntry, type CloudPrincipal, type CloudRule, type CloudRuleRow, type DiscordEntry,
} from "../api";
import { LocalTime, Status, TableWrap } from "./common";

const who = (g: { name?: string; id: string }) => (g.name && g.name !== "?" ? g.name : g.id);
const isId = (text: string) => /^\d{17,20}$/.test(text);
const LEVEL: Record<CloudLevel, string> = { view: "View", edit: "Edit", admin: "Admin" };
const LEVEL_HELP = "View = download. Edit = also upload, new folder, rename, move and delete. Admin = also these permissions.";

/** One box for roles and people (user, 2026-11-16: adding someone must be easy): click it for the server's roles,
 *  type a name to find roles and people, or paste a Discord id. One click on a match picks it. */
export function PrincipalSearch({ roles, onPick, taken, placeholder, disabled }: {
  roles: DiscordEntry[] | null;
  onPick: (p: CloudPrincipal) => void;
  taken?: (type: "role" | "user", id: string) => boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [people, setPeople] = useState<{ id: string; name: string; from: string }[] | null>(null);
  const term = text.trim();
  const searching = term.length >= 2 && !isId(term);

  useEffect(() => {
    setPeople(null);
    if (!searching) return;
    let current = true;
    const timer = setTimeout(() => { // while typing: one request when they pause
      findCloudPeople(term).then((r) => current && setPeople(r.people), () => current && setPeople([]));
    }, 300);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [searching, term]);

  const lower = term.toLowerCase();
  const roleHits = (roles ?? []).filter((r) => !taken?.("role", r.id) && (!term || r.name.toLowerCase().includes(lower) || r.id === term));
  const peopleHits = (people ?? []).filter((p) => !taken?.("user", p.id));
  const pasted = isId(term) && !roleHits.some((r) => r.id === term);
  const pick = (p: CloudPrincipal) => {
    onPick(p);
    setText("");
    setOpen(false);
  };

  return (
    <div className="person-picker" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <input
        type="search"
        aria-label="Find a role or a person"
        placeholder={placeholder ?? "Add a role or a person: click, or type a name"}
        value={text}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
      />
      {open && (
        <ul className="person-found">
          {roleHits.map((r) => (
            <li key={`role-${r.id}`}>
              <button type="button" className="link" onClick={() => pick({ type: "role", id: r.id, name: r.name })}>
                <span className="tag">Role</span> {r.name}
              </button>
            </li>
          ))}
          {peopleHits.map((p) => (
            <li key={`user-${p.id}`}>
              <button type="button" className="link" onClick={() => pick({ type: "user", id: p.id, name: p.name })}>
                <span className="tag">Person</span> {p.name}
              </button>{" "}
              <span className="muted">{p.from}</span> <code>{p.id}</code>
            </li>
          ))}
          {pasted && (
            <li>
              <button type="button" className="link" onClick={() => pick({ type: "user", id: term, name: "?" })}>
                <span className="tag">Person</span> with Discord id {term}
              </button>
              {!roles && (
                <>
                  {" · "}
                  <button type="button" className="link" onClick={() => pick({ type: "role", id: term, name: "?" })}>
                    <span className="tag">Role</span> with this id
                  </button>
                </>
              )}
            </li>
          )}
          {searching && !people && <li className="muted">Looking for people…</li>}
          {!roleHits.length && !peopleHits.length && !pasted && (!searching || people) && (
            <li className="muted">
              {term.length < 2 && !roles
                ? "Type a name (2 letters or more), or paste a Discord id."
                : term.length < 2
                  ? "Every role is already listed. Type a person's name."
                  : "Nobody found by that name. Paste their Discord user id (in Discord: right-click the person > Copy User ID)."}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/** Admins of the folder (Cloud admins, or listed as Admin on it or above it): who a folder is shared
 *  with (View / Edit / Admin) and whether it is private. Folders only: a file follows the folder it is in.
 *  One folder: every click is saved at once (add, remove, level, private). Several folders: one list, then Apply. */
export function CloudPermissions({ paths, onClose, onSaved }: { paths: string[]; onClose: () => void; onSaved: () => void }) {
  const path = paths[0];
  const many = paths.length > 1;
  const [rule, setRule] = useState<CloudRule | null>(null);
  const [isPrivate, setPrivate] = useState(false);
  const [grants, setGrants] = useState<CloudGrant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [others, setOthers] = useState<CloudRuleRow[]>([]); // rules to copy from
  const [history, setHistory] = useState<CloudLogEntry[] | string | null>(null); // a string: why it cannot be shown
  // who gets in: asked only when opened (it asks Discord for people's roles, the box does not wait for that)
  const [checking, setChecking] = useState(false);
  const [effective, setEffective] = useState<CloudEffective[] | null>(null);
  const key = paths.join("\n");

  useEffect(() => {
    let current = true;
    setRule(null);
    setError(null);
    setSaved(false);
    setHistory(null);
    setEffective(null);
    getCloudRule(path).then(
      (r) => current && (setRule(r), setPrivate(many ? false : r.private), setGrants(many ? [] : r.grants)),
      (e: Error) => current && setError(e.message),
    );
    getCloudRules().then((r) => current && setOthers(r.rules.filter((o) => many || o.path !== path)), () => {});
    return () => {
      current = false;
    };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  /** One folder: saved now (the list shows it at once; a refusal puts it back). Several: kept until Apply. */
  async function change(nextPrivate: boolean, nextGrants: CloudGrant[]) {
    const before = { isPrivate, grants };
    setPrivate(nextPrivate);
    setGrants(nextGrants);
    setSaved(false);
    setError(null);
    if (many) return;
    setBusy(true);
    try {
      const now = await setCloudRule(path, nextPrivate, nextGrants);
      if ("grants" in now) {
        setRule(now);
        setPrivate(now.private);
        setGrants(now.grants);
      }
      setSaved(true);
      setHistory(null);
      setEffective(null);
      onSaved();
    } catch (e) {
      setPrivate(before.isPrivate);
      setGrants(before.grants);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function applyToAll() {
    setBusy(true);
    setError(null);
    try {
      for (const p of paths) await setCloudRule(p, isPrivate, grants);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onSaved(); // also after a failure part-way: the rows show what was set
    }
  }

  useEffect(() => { // open, and nothing loaded (first time, or a change was just saved): ask
    if (!checking || effective || many) return;
    let current = true;
    getCloudEffective(path).then((r) => current && setEffective(r.effective), (e: Error) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [checking, effective, many, path]);

  function showHistory(open: boolean) {
    if (!open || history) return;
    getCloudLog(path).then(
      (rows) => setHistory(rows.filter((r) => r.path === path || r.path.startsWith(`${path}/`) || r.detail === path).slice(0, 30)),
      () => setHistory("Only Cloud admins of the whole cloud can read the Cloud audit log."),
    );
  }

  return (
    <div className="panel cloud-permissions" role="dialog" aria-label={many ? `Permissions for ${paths.length} folders` : `Permissions for ${path}`}>
      <div className="cloud-permissions-head">
        <h2>Who can open {many ? `these ${paths.length} folders` : path}</h2>
        {busy && <span className="muted">Saving…</span>}
        {saved && !busy && !error && <span className="ok-note">Saved</span>}
        <button className="secondary" onClick={onClose}>Close</button>
      </div>
      {many && <p className="muted cloud-name">{paths.join(" · ")}</p>}
      {error && <p className="error">{error}</p>}
      {!rule ? (
        !error && <Status loading error={null} />
      ) : (
        <>
          {!many && rule.above.map((a) => (
            <p key={a.path} className="muted">
              The folder <strong>{a.path}</strong> above it{" "}
              {a.private ? "is private" : "is shared"}
              {a.grants.length > 0 && `: ${a.grants.map((g) => `${who(g)} (${g.level})`).join(", ")}`}. That applies here
              too{a.private && !isPrivate ? "; people you add below get into this folder anyway" : ""}.
            </p>
          ))}
          <PrincipalSearch
            roles={rule.server_roles}
            disabled={busy}
            taken={(type, id) => grants.some((g) => g.type === type && g.id === id)}
            onPick={(p) => change(isPrivate, [...grants, { type: p.type, id: p.id, level: "view", name: p.name }])}
          />
          <ul className="permission-list">
            {grants.map((g) => (
              <li key={`${g.type}-${g.id}`}>
                <span className="tag">{g.type === "role" ? "Role" : "Person"}</span>
                <span className="permission-name">{who(g)}</span>
                <select
                  aria-label={`Access for ${who(g)}`}
                  title={LEVEL_HELP}
                  value={g.level}
                  disabled={busy}
                  onChange={(e) => change(isPrivate, grants.map((x) => (x === g ? { ...g, level: e.target.value as CloudLevel } : x)))}
                >
                  <option value="view">View</option>
                  <option value="edit">Edit</option>
                  <option value="admin">Admin</option>
                </select>
                <button className="link danger" disabled={busy} onClick={() => change(isPrivate, grants.filter((x) => x !== g))}>
                  Remove
                </button>
              </li>
            ))}
            {!grants.length && (
              <li className="muted">{isPrivate ? "Nobody added: only admins can see it" : "Nobody added here yet"}</li>
            )}
          </ul>
          <p className="muted">{LEVEL_HELP} New people start with View.</p>
          <label className="cloud-permissions-private">
            <input type="checkbox" checked={isPrivate} disabled={busy} onChange={(e) => change(e.target.checked, grants)} />
            <span>
              <strong>Private</strong>: only the roles and people above (and admins) can see {many ? "these folders" : "this folder"}.
              Off: everyone with Cloud view or Cloud edit on the whole cloud gets in as well.
            </span>
          </label>
          {others.length > 0 && (
            <label className="cloud-permissions-copy">
              <span className="muted">Same people as another folder:</span>{" "}
              <select
                aria-label="Copy the permissions of another folder"
                value=""
                disabled={busy}
                onChange={(e) => {
                  const from = others.find((o) => o.path === e.target.value);
                  if (!from) return;
                  if (many || (!grants.length && !isPrivate) || window.confirm(`Replace the permissions of ${path} with those of ${from.path}?`)) {
                    change(from.private, from.grants);
                  }
                }}
              >
                <option value="">Copy from…</option>
                {others.map((o) => (
                  <option key={o.path} value={o.path}>
                    {o.path} ({[o.private ? "private" : "", o.grants.length ? `${o.grants.length} listed` : ""].filter(Boolean).join(", ")})
                  </option>
                ))}
              </select>
            </label>
          )}
          {many && (
            <div className="cloud-actions">
              <button disabled={busy || saved} onClick={applyToAll}>{busy ? "Saving…" : `Apply to ${paths.length} folders`}</button>
              <span className="muted">Replaces the permissions each of them has now.</span>
            </div>
          )}
          {!many && (
            <details className="cloud-permissions-more" onToggle={(e) => setChecking(e.currentTarget.open)}>
              <summary>Check: who gets in</summary>
              {!effective && <Status loading error={null} />}
              <ul className="permission-list">
                {(effective ?? []).map((p) => (
                  <li key={`${p.type}-${p.id}`} className={p.level ? undefined : "muted"}>
                    <span className="tag">{p.type === "role" ? "Role" : "Person"}</span>
                    <span className="permission-name">{who(p)}</span>
                    <span className="tag">{p.level ? LEVEL[p.level] : "No access"}</span>
                  </li>
                ))}
              </ul>
              <p className="muted">
                Everyone with a whole-cloud permission or added on this folder or one above it. A role stands for someone with
                only that role; a person with several gets the highest of them. Cloud admins and the admins of a folder
                above always get in.
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
                <p className="muted">Nothing in the Cloud audit log for this folder.</p>
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
            Files have no permissions of their own: a file follows the folder it is in. Someone who is logged in sees a change
            within 5 minutes, or at once after logging out and in again.
          </p>
        </>
      )}
    </div>
  );
}

const WHOLE: { key: CloudPermission; title: string; gives: string }[] = [
  { key: "cloud_view", title: "Cloud view", gives: "See and download everything that is not private." },
  { key: "cloud_edit", title: "Cloud edit", gives: "Also upload, new folder, rename, move and delete. Includes Cloud view." },
  {
    key: "cloud_admin",
    title: "Cloud admin",
    gives: "Also decides who gets in (these lists and every folder), and has the recycle bin, quarantine and audit log. Sees everything, private or not.",
  },
];

/** Cloud admins: who has Cloud view / edit / admin on the whole cloud (user, 2026-11-16: set here, not in the
 *  Console; a console user has no Cloud permission by being one). One click adds or removes, saved at once. */
export function CloudAccessPanel() {
  const [state, setState] = useState<CloudAccessState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getCloudAccess().then(setState, (e: Error) => setError(e.message));
  }, []);

  async function change(c: Parameters<typeof changeCloudAccess>[0]) {
    setBusy(true);
    setError(null);
    try {
      setState(await changeCloudAccess(c));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="cloud-rules">
      <h2>Who has the whole cloud</h2>
      <p className="muted">
        For everything in the cloud that is not private. To give someone one folder only, use <strong>Permissions</strong> beside
        that folder instead. The Cloud is separate from the Console: a console user gets in only when listed here.
      </p>
      {error && <p className="error">{error}</p>}
      {!state ? (
        !error && <Status loading error={null} />
      ) : (
        <div className="permissions">
          {WHOLE.map(({ key, title, gives }) => {
            const { roles, users } = state.permissions[key];
            const rows = [...roles.map((e) => ({ ...e, type: "role" as const })), ...users.map((e) => ({ ...e, type: "user" as const }))];
            const fixed = key === "cloud_admin" ? state.fixed : [];
            return (
              <article key={key} className="panel permission-card">
                <h2>{title}</h2>
                <p className="muted">{gives}</p>
                <ul className="permission-list">
                  {fixed.map((e) => (
                    <li key={`fixed-${e.id}`}>
                      <span className="tag">{e.type === "role" ? "Role" : "Person"}</span>
                      <span className="permission-name">{who(e)}</span>
                      <span className="tag" title="The owner, set in ECHOVR_DISCORD_PREVIEW_ROLES (the YAML): always Cloud admin, so the cloud cannot be locked">
                        Owner, fixed
                      </span>
                    </li>
                  ))}
                  {rows.map((e) => (
                    <li key={`${e.type}-${e.id}`}>
                      <span className="tag">{e.type === "role" ? "Role" : "Person"}</span>
                      <span className="permission-name">{who(e)}</span>
                      <button
                        className="link danger"
                        disabled={busy}
                        onClick={() => change({ permission: key, type: e.type, id: e.id, remove: true })}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                  {!fixed.length && !rows.length && <li className="muted">Nobody yet</li>}
                </ul>
                <PrincipalSearch
                  roles={state.server_roles}
                  disabled={busy}
                  taken={(type, id) => rows.some((e) => e.type === type && e.id === id) || fixed.some((e) => e.id === id)}
                  onPick={(p) => change({ permission: key, type: p.type, id: p.id })}
                />
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** Every folder with permissions of its own that this person is admin of, in one list ("All permissions" on the
 *  Cloud page). */
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
      (row.exists ? "It is then open to whoever has access to the folder it is in." : "The folder itself is gone; only its left-over permissions are removed."))) return;
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
        Set with <strong>Permissions</strong> beside a folder on the Cloud page; files follow the folder they are in.
        Everything else follows the whole-cloud permissions (Cloud view / edit / admin).
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
                    {!r.exists && <><span className="tag" title="Removed outside the site (File Station). The permissions would apply again to anything that gets this name">Folder is gone</span>{" "}</>}
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
