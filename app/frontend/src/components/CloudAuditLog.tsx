import { useEffect, useState } from "react";
import { getCloudLog, type CloudLogEntry } from "../api";
import { fileSize } from "../format";
import { LocalTime, Status, TableWrap } from "./common";

const ACTION_LABEL: Record<CloudLogEntry["action"], string> = {
  upload: "Upload", download: "Download", folder: "New folder", rename: "Rename", delete: "Delete", restore: "Restore",
  purge: "Removed for good", scan: "Virus scan", virus: "Virus found", release: "Released", denied: "Refused",
};

/** Console users: every upload, download, change and refusal, newest first, with search. */
export function CloudAuditLog() {
  const [rows, setRows] = useState<CloudLogEntry[] | null>(null);
  const [term, setTerm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    let current = true;
    const timer = setTimeout(() => {
      getCloudLog(term.trim()).then(
        (r) => current && (setRows(r), setMore(r.length === 100), setError(null)),
        (e: Error) => current && setError(e.message),
      );
    }, 300); // while typing: one request when they pause
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [term]);

  async function loadMore() {
    if (!rows?.length) return;
    try {
      const next = await getCloudLog(term.trim(), rows[rows.length - 1].id);
      setRows([...rows, ...next]);
      setMore(next.length === 100);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="cloud-log">
      <h2>Cloud audit log</h2>
      <p className="muted">Every upload, download, new folder, rename and delete, and every refused attempt by someone logged in. Only console users see this.</p>
      <input
        type="search"
        aria-label="Search the audit log"
        placeholder="Search: person, Discord id, file or action"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      {!rows ? (
        !error && <Status loading error={null} />
      ) : rows.length === 0 ? (
        <p className="muted">{term ? "Nothing matches." : "Nothing yet."}</p>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>File</th>
                <th className="num">Size</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.ok ? undefined : "cloud-log-refused"}>
                  <td data-label="When" className="nowrap"><LocalTime iso={r.at} /></td>
                  <td data-label="Who"><span title={r.who_id}>{r.who}</span></td>
                  <td data-label="Action">
                    {r.ok ? ACTION_LABEL[r.action] : <span className="error">{r.action === "denied" ? "Refused" : `${ACTION_LABEL[r.action]} refused`}</span>}
                  </td>
                  <td data-label="File" className="cloud-name">
                    {r.path}
                    {r.detail && <span className="muted"> {r.action === "rename" ? `→ ${r.detail}` : `(${r.detail})`}</span>}
                  </td>
                  <td data-label="Size" className="num">{r.size === null ? "" : fileSize(r.size)}</td>
                  <td data-label="IP"><code>{r.ip ?? ""}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
      {more && (
        <button className="secondary" onClick={loadMore}>
          Older entries
        </button>
      )}
    </section>
  );
}
