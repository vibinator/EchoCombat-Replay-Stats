import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import {
  cloudDownloadUrl, deleteCloud, getCloud, getMe, loginUrl, makeCloudFolder, renameCloud, uploadCloudFile,
  type CloudEntry, type CloudListing,
} from "../api";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = n / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`;
}

const join = (folder: string, name: string) => (folder ? `${folder}/${name}` : name);

interface Upload {
  name: string;
  size: number;
  sent: number;
  error?: string;
}

/** Open Cloud: files for Discord members with Cloud view (download) or Cloud edit (also upload, rename, delete). */
export function CloudPage() {
  usePageTitle("Cloud");
  const me = useApi(getMe, "me");
  const user = me.data?.user;
  if (me.loading && !me.data) return <Status loading error={null} />;
  if (!user) {
    return (
      <section>
        <h1>Cloud</h1>
        <p>Log in with Discord to open the cloud files.</p>
        {me.data?.enabled && (
          <a className="button discord-login" href={loginUrl("/cloud")}>
            Log in with Discord
          </a>
        )}
      </section>
    );
  }
  if (!user.cloud) {
    return (
      <section>
        <h1>Cloud</h1>
        <p className="muted">Your Discord account does not have Cloud access. Ask a console user to give it to you on the Permissions page.</p>
      </section>
    );
  }
  return <CloudBrowser />;
}

function CloudBrowser() {
  const [params, setParams] = useSearchParams();
  const folder = params.get("path") ?? "";
  const [listing, setListing] = useState<CloudListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    getCloud(folder).then(
      (l) => {
        setListing(l);
        setError(null);
      },
      (e: Error) => setError(e.message),
    );
  }, [folder]);
  useEffect(() => {
    setListing(null);
    load();
  }, [load]);

  const open = (path: string) => setParams(path ? { path } : {});
  const canEdit = !!listing?.can_edit;
  const uploading = uploads.some((u) => u.sent < u.size && !u.error);

  async function act(run: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await run();
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(files: File[]) {
    if (!files.length || !listing) return;
    const existing = new Set(listing.entries.filter((e) => !e.dir).map((e) => e.name));
    const clashes = files.filter((f) => existing.has(f.name));
    const overwrite = clashes.length > 0 &&
      window.confirm(`${clashes.map((f) => f.name).join(", ")} already ${clashes.length === 1 ? "exists" : "exist"} here. Replace?`);
    const queue = files.filter((f) => overwrite || !existing.has(f.name));
    setUploads(queue.map((f) => ({ name: f.name, size: f.size, sent: 0 })));
    for (const [i, file] of queue.entries()) {
      const set = (patch: Partial<Upload>) => setUploads((list) => list.map((u, j) => (j === i ? { ...u, ...patch } : u)));
      try {
        await uploadCloudFile(folder, file, overwrite, (sent) => set({ sent }));
        set({ sent: file.size });
      } catch (e) {
        set({ error: (e as Error).message });
      }
    }
    load();
  }

  function rename(entry: CloudEntry) {
    const name = window.prompt(`New name for ${entry.name}`, entry.name);
    if (name && name.trim() && name.trim() !== entry.name) act(() => renameCloud(join(folder, entry.name), name.trim()));
  }

  function remove(entry: CloudEntry) {
    const what = entry.dir ? `the folder ${entry.name} and everything in it` : entry.name;
    if (window.confirm(`Delete ${what}? This cannot be undone.`)) act(() => deleteCloud(join(folder, entry.name)));
  }

  function newFolder() {
    const name = window.prompt("Folder name");
    if (name && name.trim()) act(() => makeCloudFolder(folder, name.trim()));
  }

  const crumbs = folder ? folder.split("/") : [];
  return (
    <section
      className="cloud"
      onDragOver={(e) => {
        if (!canEdit) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={(e) => {
        if (!canEdit) return;
        e.preventDefault();
        setDragging(false);
        if (!uploading) upload(Array.from(e.dataTransfer.files));
      }}
    >
      <h1>Cloud</h1>
      <nav className="cloud-crumbs" aria-label="Folder">
        <button className="link" onClick={() => open("")}>Cloud</button>
        {crumbs.map((part, i) => (
          <span key={i}>
            {" / "}
            {i === crumbs.length - 1 ? <strong>{part}</strong> : <button className="link" onClick={() => open(crumbs.slice(0, i + 1).join("/"))}>{part}</button>}
          </span>
        ))}
      </nav>
      {listing && (
        <p className="muted">
          {bytes(listing.used_bytes)} used{listing.quota_bytes ? ` of ${bytes(listing.quota_bytes)}` : ""}
          {!canEdit && " · you can download files; changing them needs Cloud edit"}
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {canEdit && (
        <>
          <div className="cloud-actions">
            <button className="secondary" disabled={busy} onClick={newFolder}>New folder</button>
          </div>
          <div
            className={`upload-drop${dragging ? " dragging" : ""}${uploading ? " busy" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => !uploading && input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !uploading && input.current?.click()}
          >
            <span className="upload-drop-title">{uploading ? "Uploading…" : "Upload files"}</span>
            <span className="muted">Click to choose, or drop files anywhere on this page</span>
            <input
              ref={input}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                upload(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
          </div>
          {uploads.length > 0 && (
            <ul className="cloud-uploads">
              {uploads.map((u, i) => (
                <li key={i}>
                  <span className="permission-name">{u.name}</span>
                  {u.error ? (
                    <span className="error">{u.error}</span>
                  ) : (
                    <div className="progress">
                      <div style={{ width: `${u.size ? (100 * u.sent) / u.size : 100}%` }} />
                      <span>{u.sent >= u.size ? "Done" : `${bytes(u.sent)} of ${bytes(u.size)}`}</span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {!listing ? (
        !error && <Status loading error={null} />
      ) : listing.entries.length === 0 ? (
        <EmptyState title="This folder is empty">{canEdit ? "Upload files or make a folder." : undefined}</EmptyState>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Size</th>
                <th>Changed</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {folder && (
                <tr>
                  <td colSpan={4}>
                    <button className="link" onClick={() => open(crumbs.slice(0, -1).join("/"))}>.. (up one folder)</button>
                  </td>
                </tr>
              )}
              {listing.entries.map((e) => (
                <tr key={e.name}>
                  <td data-label="Name" className="cloud-name">
                    {e.dir ? (
                      <><span className="tag">Folder</span> <button className="link" onClick={() => open(join(folder, e.name))}>{e.name}</button></>
                    ) : (
                      <a href={cloudDownloadUrl(join(folder, e.name))} download={e.name}>{e.name}</a>
                    )}
                  </td>
                  <td data-label="Size" className="num">{e.size === null ? "" : bytes(e.size)}</td>
                  <td data-label="Changed">{new Date(e.modified * 1000).toLocaleString()}</td>
                  <td className="cloud-row-actions">
                    {!e.dir && <a href={cloudDownloadUrl(join(folder, e.name))} download={e.name}>Download</a>}
                    {canEdit && (
                      <>
                        <button className="link" disabled={busy} onClick={() => rename(e)}>Rename</button>
                        <button className="link danger" disabled={busy} onClick={() => remove(e)}>Delete</button>
                      </>
                    )}
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
