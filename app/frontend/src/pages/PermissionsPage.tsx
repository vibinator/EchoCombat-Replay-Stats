import { useEffect, useState } from "react";
import { Navigate } from "react-router";
import { changePermission, getPermissions, type DiscordEntry, type Permission, type PermissionState } from "../api";
import { Status } from "../components/common";

const PERMISSIONS: { key: Permission; title: string; gives: string }[] = [
  {
    key: "admin",
    title: "Admin",
    gives: "The Status page (live progress of replay processing). Includes the Preview and Cloud admin.",
  },
  {
    key: "console",
    title: "Console",
    gives: "The Console, with this Permissions tab: every admin.bat command on the website. Includes the Preview. Does not include the Cloud.",
  },
  { key: "preview", title: "Preview", gives: "Echo Combat challenges and Mega Prizes before the launch date." },
];

/** Old /permissions address: the panel now lives on the Console page, which does the access check. */
export function PermissionsPage() {
  return <Navigate to="/console?tab=permissions" replace />;
}

/** The permissions panel, a tab of the Console (console users only; the server checks every change). */
export function Permissions() {
  const [state, setState] = useState<PermissionState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPermissions().then(setState, (e: Error) => setError(e.message));
  }, []);
  async function change(c: Parameters<typeof changePermission>[0]): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      setState(await changePermission(c));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="permissions">
      <h2>Permissions</h2>
      <p className="muted">
        Give or take away a permission for a Discord role (everyone with that role) or for one person by their Discord user id. A change
        applies straight away; people who are logged in see it within 5 minutes, or at once after logging out and in again. The Cloud
        has its own permissions (View, Edit and Admin), which Cloud admins set on the Cloud page under All permissions. The Admin
        permission above includes Cloud admin.
      </p>
      {error && <p className="error">{error}</p>}
      {!state ? (
        <Status loading={!error} error={null} />
      ) : (
        <>
          {state.server_roles === null && (
            <p className="muted">The bot could not list the Discord server's roles, so roles are added by id and shown without names.</p>
          )}
          <div className="permissions">
            {PERMISSIONS.map((p) => (
              <PermissionCard key={p.key} permission={p.key} title={p.title} gives={p.gives} state={state} busy={busy} change={change} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function PermissionCard({
  permission,
  title,
  gives,
  state,
  busy,
  change,
}: {
  permission: Permission;
  title: string;
  gives: string;
  state: PermissionState;
  busy: boolean;
  change: (c: Parameters<typeof changePermission>[0]) => Promise<boolean>;
}) {
  const [type, setType] = useState<"role" | "user">("role");
  const [id, setId] = useState("");
  const { roles, users } = state.permissions[permission];
  const fixed = permission === "console" ? state.fixed : [];
  const available = (state.server_roles ?? []).filter((r) => !roles.some((x) => x.id === r.id));

  function remove(entry: DiscordEntry, kind: "role" | "user") {
    const what = kind === "role" ? `everyone with the role ${entry.name}` : entry.name === "?" ? entry.id : entry.name;
    if (window.confirm(`Take the ${title} permission away from ${what}?`)) change({ permission, type: kind, id: entry.id, remove: true });
  }

  return (
    <article className="panel permission-card">
      <h2>{title}</h2>
      <p className="muted">{gives}</p>
      <ul className="permission-list">
        {fixed.map((e) => (
          <li key={`fixed-${e.id}`}>
            <span className="tag">{e.type === "role" ? "Role" : "User"}</span>
            <span className="permission-name">{e.name}</span>
            <code>{e.id}</code>
            <span className="tag" title="Set in ECHOVR_DISCORD_PREVIEW_ROLES in the YAML file: it cannot be removed here, change it there">
              YAML, fixed
            </span>
          </li>
        ))}
        {roles.map((e) => (
          <li key={`role-${e.id}`}>
            <span className="tag">Role</span>
            <span className="permission-name">{e.name}</span>
            <code>{e.id}</code>
            <button className="link danger" disabled={busy} onClick={() => remove(e, "role")}>
              Remove
            </button>
          </li>
        ))}
        {users.map((e) => (
          <li key={`user-${e.id}`}>
            <span className="tag">User</span>
            <span className="permission-name">{e.name}</span>
            <code>{e.id}</code>
            <button className="link danger" disabled={busy} onClick={() => remove(e, "user")}>
              Remove
            </button>
          </li>
        ))}
        {!fixed.length && !roles.length && !users.length && <li className="muted">Nobody yet</li>}
      </ul>
      <form
        className="permission-add"
        onSubmit={async (e) => {
          e.preventDefault();
          if (id.trim() && (await change({ permission, type, id: id.trim() }))) setId("");
        }}
      >
        <select
          aria-label="Add a role or a person"
          value={type}
          onChange={(e) => {
            setType(e.target.value as "role" | "user");
            setId("");
          }}
        >
          <option value="role">Role</option>
          <option value="user">User</option>
        </select>
        {type === "role" && state.server_roles ? (
          <select aria-label="Role" value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">Choose a role…</option>
            {available.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-label={type === "role" ? "Role id" : "Discord user id"}
            placeholder={type === "role" ? "Role id" : "Discord user id (right-click the person > Copy User ID)"}
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
        )}
        <button type="submit" disabled={busy || !id.trim()}>
          Add
        </button>
      </form>
    </article>
  );
}
