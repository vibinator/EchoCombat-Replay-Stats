import { useCallback, useEffect, useState } from "react";
import { emptyCloudTrash, getCloudTrash, purgeCloudTrash, restoreCloudTrash, type CloudTrashItem } from "../api";
import { fileSize } from "../format";
import { LocalTime, Status, TableWrap } from "./common";

const iso = (unix: number) => new Date(unix * 1000).toISOString();

/** Console > Cloud > Recycle bin: what people deleted from the cloud, restored with one click (user, 2026-11-10). */
export function CloudTrash() {
  const [data, setData] = useState<{ items: CloudTrashItem[]; bytes: number; days: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getCloudTrash().then((d) => (setData(d), setError(null)), (e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function act(run: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      setNote(await run());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      load();
    }
  }

  const restore = (i: CloudTrashItem) => act(async () => `Restored to ${(await restoreCloudTrash(i.id)).path}`);
  const purge = (i: CloudTrashItem) => {
    if (window.confirm(`Delete ${i.path} for good? It cannot be restored afterwards.`)) {
      act(async () => `${(await purgeCloudTrash(i.id)).path} deleted for good`);
    }
  };
  const empty = () => {
    if (data && window.confirm(`Delete all ${data.items.length} items in the recycle bin for good (${fileSize(data.bytes)})? They cannot be restored afterwards.`)) {
      act(async () => {
        const r = await emptyCloudTrash();
        return `${r.count} items deleted for good (${fileSize(r.size)} freed)`;
      });
    }
  };

  return (
    <section className="cloud-log">
      <h2>Cloud recycle bin</h2>
      <p className="muted">
        Files and folders deleted on the Cloud page. Restore puts them back where they were (with a new name if something new has
        taken it). {data?.days ? `Each item is deleted for good ${data.days} days after it was deleted. ` : ""}
        The recycle bin counts toward the cloud's space.
      </p>
      {note && <p className="ok-note" role="status">{note}</p>}
      {error && <p className="error">{error}</p>}
      {!data ? (
        !error && <Status loading error={null} />
      ) : data.items.length === 0 ? (
        <p className="muted">The recycle bin is empty.</p>
      ) : (
        <>
          <p>
            <strong>{data.items.length} items · {fileSize(data.bytes)}</strong>{" "}
            <button className="link danger" disabled={busy} onClick={empty}>Empty the recycle bin</button>
          </p>
          <TableWrap>
            <table className="stack">
              <thead>
                <tr>
                  <th>Deleted</th>
                  <th>By</th>
                  <th>Item</th>
                  <th className="num">Size</th>
                  <th>Deleted for good</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((i) => (
                  <tr key={i.id}>
                    <td data-label="Deleted" className="nowrap"><LocalTime iso={iso(i.deleted_at)} /></td>
                    <td data-label="By"><span title={i.by_id}>{i.by_name}</span></td>
                    <td data-label="Item" className="cloud-name">
                      {i.dir && <span className="tag">Folder</span>} {i.path}
                    </td>
                    <td data-label="Size" className="num">{fileSize(i.size)}</td>
                    <td data-label="Deleted for good" className="nowrap">{i.expires_at ? <LocalTime iso={iso(i.expires_at)} /> : "never"}</td>
                    <td>
                      <div className="cloud-row-actions">
                        <button disabled={busy} onClick={() => restore(i)}>Restore</button>
                        <button className="link danger" disabled={busy} onClick={() => purge(i)}>Delete forever</button>
                      </div>
                    </td>
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
