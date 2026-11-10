import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { droppedEntries, pickedFolder, readEntries, useUploadQueue, type Picked } from "../components/cloudUploads";
import {
  cloudDownloadUrl, deleteCloud, getCloud, getMe, loginUrl, makeCloudFolder, renameCloud,
  type CloudEntry, type CloudListing,
} from "../api";
import { fileSize } from "../format";
import { LocalTime, Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const join = (folder: string, name: string) => (folder ? `${folder}/${name}` : name);

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
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false); // a dropped folder is being read
  const filesInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

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
  const checking = !!listing?.entries.some((e) => e.state === "scanning");
  useEffect(() => { // files waiting for their virus scan: look again until they are through
    if (!checking) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [checking, load]);

  const open = (path: string) => setParams(path ? { path } : {});
  const canEdit = !!listing?.can_edit;
  const queue = useUploadQueue(load);
  useEffect(() => { // React has no prop for it: the folder picker (Windows' "Select folder" dialog)
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, [canEdit]);

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

  /** Adds files to the queue (it may be running already). Names already in this folder: asked once whether to replace. */
  function upload(picked: Picked[], dirs: string[] = []) {
    if ((!picked.length && !dirs.length) || !listing) return;
    const existing = new Set(listing.entries.map((e) => e.name));
    const top = new Set([...picked.map((p) => p.dir.split("/")[0] || p.file.name), ...dirs.map((d) => d.split("/")[0])]);
    const clashes = [...top].filter((n) => existing.has(n));
    const overwrite = clashes.length > 0 && window.confirm(
      `${clashes.slice(0, 5).join(", ")}${clashes.length > 5 ? ` and ${clashes.length - 5} more` : ""} already ` +
      `${clashes.length === 1 ? "exists" : "exist"} here. Replace files with the same name?\n\n` +
      "OK = replace them. Cancel = keep the ones already here (new files are still added).",
    );
    if (dirs.length) queue.addFolders(folder, dirs).then(load);
    queue.add(folder, picked, overwrite);
  }

  async function drop(entries: FileSystemEntry[]) {
    setReading(true);
    try {
      const { files, dirs } = await readEntries(entries);
      upload(files, dirs);
    } catch (e) {
      setError(`Could not read what was dropped: ${(e as Error).message}`);
    } finally {
      setReading(false);
    }
  }

  function rename(entry: CloudEntry) {
    const name = window.prompt(`New name for ${entry.name}`, entry.name);
    if (name && name.trim() && name.trim() !== entry.name) act(() => renameCloud(join(folder, entry.name), name.trim()));
  }

  function remove(entry: CloudEntry) {
    const what = entry.dir ? `the folder ${entry.name} and everything in it` : entry.name;
    if (window.confirm(`Move ${what} to the recycle bin?\n\nA console user can restore it for the next 30 days.`)) {
      act(() => deleteCloud(join(folder, entry.name)));
    }
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
        const entries = droppedEntries(e.dataTransfer.items); // must be taken now: the browser empties the list after
        if (entries.length) drop(entries);
      }}
    >
      <h1>Cloud</h1>
      {folder && <nav className="cloud-crumbs" aria-label="Folder">
        <button className="link" onClick={() => open("")}>Cloud</button>
        {crumbs.map((part, i) => (
          <span key={i}>
            {" / "}
            {i === crumbs.length - 1 ? <strong>{part}</strong> : <button className="link" onClick={() => open(crumbs.slice(0, i + 1).join("/"))}>{part}</button>}
          </span>
        ))}
      </nav>}
      {listing && (
        <p className="muted">
          {fileSize(listing.used_bytes)} used{listing.quota_bytes ? ` of ${fileSize(listing.quota_bytes)}` : ""}
          {listing.trash_bytes > 0 && ` (${fileSize(listing.trash_bytes)} of it in the recycle bin)`}
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
            className={`upload-drop${dragging ? " dragging" : ""}`}
            role="button"
            tabIndex={0}
            aria-label="Upload files: opens the file dialog"
            // the whole box opens the file dialog, as before. Its buttons stop their click here and open their own dialog; the
            // hidden inputs live outside the box, so an input's click never comes back through this handler (it opened the
            // file dialog over the folder one, and a second click() on a file input while its dialog opens can cancel it)
            onClick={() => filesInput.current?.click()}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) {
                e.preventDefault();
                filesInput.current?.click();
              }
            }}
          >
            <span className="upload-drop-title">{reading ? "Reading the folder…" : "Click to choose files, or drop files and folders anywhere on this page"}</span>
            <span className="cloud-upload-buttons">
              {/* both open the system's own file dialog (Windows Explorer on a PC) */}
              <button type="button" onClick={(e) => { e.stopPropagation(); filesInput.current?.click(); }}>Upload files</button>
              <button type="button" className="secondary" onClick={(e) => { e.stopPropagation(); folderInput.current?.click(); }}>Upload folder</button>
            </span>
            <span className="muted">Many files at once, folders with everything inside them; more can be added while it uploads.</span>
          </div>
          <input ref={filesInput} type="file" multiple hidden onChange={(e) => {
            upload(Array.from(e.target.files ?? [], (file) => ({ file, dir: "" })));
            e.target.value = "";
          }} />
          <input ref={folderInput} type="file" multiple hidden onChange={(e) => {
            if (e.target.files) upload(pickedFolder(e.target.files));
            e.target.value = "";
          }} />
          <UploadSummary queue={queue} />
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
              {listing.entries.map((e) => e.state === "scanning" ? (
                <tr key={`${e.name}|scanning`} className="cloud-checking">
                  <td data-label="Name" className="cloud-name">
                    <span className="tag" title="Uploaded; it can be downloaded once the virus scan finds it clean">Checking for viruses</span>{" "}
                    {e.name}
                  </td>
                  <td data-label="Size" className="num">{e.size === null ? "" : fileSize(e.size)}</td>
                  <td data-label="Changed" className="nowrap"><LocalTime iso={new Date(e.modified * 1000).toISOString()} /></td>
                  <td />
                </tr>
              ) : (
                <tr key={e.name}>
                  <td data-label="Name" className="cloud-name">
                    {e.state === "unscanned" && (
                      <span className="tag" title="Too big for the virus scan: it was not checked">Not scanned</span>
                    )}{e.state === "unscanned" && " "}
                    {e.dir ? (
                      <><span className="tag">Folder</span> <button className="link" onClick={() => open(join(folder, e.name))}>{e.name}</button></>
                    ) : (
                      <a href={cloudDownloadUrl(join(folder, e.name))} download={e.name}>{e.name}</a>
                    )}
                  </td>
                  <td data-label="Size" className="num">{e.size === null ? "" : fileSize(e.size)}</td>
                  <td data-label="Changed" className="nowrap"><LocalTime iso={new Date(e.modified * 1000).toISOString()} /></td>
                  <td>
                    <div className="cloud-row-actions">
                      {!e.dir && <a href={cloudDownloadUrl(join(folder, e.name))} download={e.name}>Download</a>}
                      {canEdit && (
                        <>
                          <button className="link" disabled={busy} onClick={() => rename(e)}>Rename</button>
                          <button className="link danger" disabled={busy} onClick={() => remove(e)}>Delete</button>
                        </>
                      )}
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

/** One line for the whole queue, the files being sent now, and the ones that failed (not hundreds of bars). */
function UploadSummary({ queue }: { queue: ReturnType<typeof useUploadQueue> }) {
  const { jobs, active } = queue;
  if (!jobs.length) return null;
  const count = (state: string) => jobs.filter((j) => j.state === state).length;
  const done = count("done"), failed = count("failed"), skipped = count("skipped");
  const total = jobs.reduce((n, j) => n + j.file.size, 0);
  const sent = jobs.reduce((n, j) => n + (j.state === "done" || j.state === "skipped" ? j.file.size : j.sent), 0);
  const sending = jobs.filter((j) => j.state === "sending");
  const failures = jobs.filter((j) => j.state === "failed");
  return (
    <div className="cloud-uploads">
      <div className="cloud-uploads-head">
        <strong>
          {active
            ? `Uploading: ${done + skipped} of ${jobs.length} files done${sending.length ? ` · ${sending.length} sending` : ""}`
            : `Uploaded ${done} of ${jobs.length} files`}
          {" · "}{fileSize(sent)} of {fileSize(total)}
        </strong>
        {skipped > 0 && <span className="muted"> · {skipped} already here, kept</span>}
        {failed > 0 && <span className="error"> · {failed} failed</span>}
        {!active && failed > 0 && <button type="button" className="link" onClick={queue.retryFailed}>Try the failed ones again</button>}
        {!active && <button type="button" className="link" onClick={queue.clearFinished}>Clear</button>}
      </div>
      <div className="progress">
        <div style={{ width: `${total ? (100 * sent) / total : 100}%` }} />
        <span>{total ? `${Math.floor((100 * sent) / total)} %` : "Done"}</span>
      </div>
      {sending.length > 0 && (
        <ul>
          {sending.map((j) => (
            <li key={j.id}>
              <span className="cloud-name">{[j.target, j.file.name].filter(Boolean).join("/")}</span>
              <span className="muted"> {fileSize(j.sent)} of {fileSize(j.file.size)}</span>
            </li>
          ))}
        </ul>
      )}
      {failures.length > 0 && (
        <ul>
          {failures.slice(0, 20).map((j) => (
            <li key={j.id}>
              <span className="cloud-name">{[j.target, j.file.name].filter(Boolean).join("/")}</span>
              <span className="error"> {j.error}</span>
            </li>
          ))}
          {failures.length > 20 && <li className="muted">and {failures.length - 20} more</li>}
        </ul>
      )}
    </div>
  );
}

