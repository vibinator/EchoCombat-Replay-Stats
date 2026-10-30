import { useState } from "react";
import {
  ADMIN_XLSX_URL,
  forgetResponses,
  getAdminAchievements,
  getIconChoices,
  getMe,
  loginUrl,
  setIcon,
  uploadIcon,
  type IconRow,
} from "../api";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";

/** Discord admins only (D42). Read-only: changes are still made in the admin console (admin.bat). */
export function AdminPage() {
  const me = useApi(getMe, "me");
  if (!me.data) return <Status loading={me.loading} error={me.error} />;
  const user = me.data.user;
  if (!user?.admin)
    return (
      <section>
        <h1>Admin</h1>
        <EmptyState title="Admins only">
          {!me.data.enabled ? (
            "Discord login is not set up on this server."
          ) : user ? (
            <>Logged in as {user.name}, but your Discord account does not have an admin role.</>
          ) : (
            <a href={loginUrl("/admin")}>Log in with Discord</a>
          )}
        </EmptyState>
      </section>
    );
  return <AdminAchievements />;
}

export const IMG = "/achievements/";
export const GENERIC_ICON = "happy_cubesat.png";

/** Icon picker for one achievement (D43): Admin tab and the Console page's achievement export. */
export function IconEditor({ row, onDone }: { row: IconRow; onDone: (changed: boolean) => void }) {
  const choices = useApi(getIconChoices, `icon-choices-${row.icon}`); // an upload adds a choice
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(change: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await change();
      forgetResponses();
      onDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel icon-editor" role="dialog" aria-label={`Icon for ${row.name}`}>
      <div className="section-head">
        <h2>
          Icon for #{row.id} {row.name}
        </h2>
        <button className="secondary" onClick={() => onDone(false)}>
          Close
        </button>
      </div>
      <p className="muted">
        Current: <img className="icon-thumb" src={IMG + (row.icon ?? GENERIC_ICON)} alt="" /> Click an icon to use it, or upload a PNG (at most
        512 KB, 1024 x 1024). The change shows on the website straight away.
      </p>
      <div className="filters">
        <label className="button secondary">
          Upload PNG…
          <input
            type="file"
            accept="image/png"
            hidden
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) run(() => uploadIcon(row.id, file));
            }}
          />
        </label>
        <button className="secondary" disabled={busy || row.icon === row.default_icon} onClick={() => run(() => setIcon(row.id, null))}>
          Reset to default
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <Status loading={choices.loading} error={choices.error} />
      <div className="icon-grid">
        {choices.data?.map((icon) => (
          <button
            key={icon}
            className={icon === row.icon ? "icon-choice active" : "icon-choice"}
            title={icon}
            disabled={busy}
            onClick={() => run(() => setIcon(row.id, icon))}
          >
            <img src={IMG + icon} alt={icon} loading="lazy" />
          </button>
        ))}
      </div>
    </div>
  );
}

function AdminAchievements() {
  const [version, setVersion] = useState(0);
  const list = useApi(getAdminAchievements, `admin-achievements-${version}`);
  const [editing, setEditing] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const term = q.trim().toLowerCase();
  const items = (list.data?.items ?? []).filter((r) => !term || Object.values(r).some((v) => String(v).toLowerCase().includes(term)));

  return (
    <section>
      <div className="section-head">
        <h1>Admin · Achievements and challenges</h1>
        <a className="button" href={ADMIN_XLSX_URL} download>
          Download Excel
        </a>
      </div>
      <p className="muted">
        Every achievement and Flamingo Challenge, with how to get it. Built from the live rules, so this list and the Excel file always match the
        website. Requirement = the text players see. Changes (launch date, roles, merges) are made in the admin console.
      </p>
      <input type="search" placeholder="Filter" aria-label="Filter achievements" value={q} onChange={(e) => setQ(e.target.value)} />
      {editing !== null && list.data && (
        <IconEditor
          row={list.data.items.find((r) => r.id === editing)!}
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
            {items.length} of {list.data.items.length}
          </p>
          <TableWrap>
            <table className="stack admin-achievements">
              <thead>
                <tr>
                  <th>Icon</th>
                  {list.data.columns.map((c) => (
                    <th key={c.key} className={c.key === "id" ? "num" : undefined}>
                      {c.label}
                    </th>
                  ))}
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
                    {list.data!.columns.map((c) => (
                      <td key={c.key} data-label={c.label} className={c.key === "id" ? "num" : undefined}>
                        {r[c.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </>
      )}
    </section>
  );
}
