import { useCallback, useEffect, useState } from "react";
import { deleteQuarantined, getCloudQuarantine, releaseQuarantined, scanAllCloudFiles, type CloudQuarantine as Q,
  type CloudQuarantineItem } from "../api";
import { fileSize } from "../format";
import { LocalTime, Status, TableWrap } from "./common";

const iso = (unix: number) => new Date(unix * 1000).toISOString();

/** Console > Cloud > Quarantine: uploads a virus scanner flagged, and how the scanners are doing (user, 2026-11-10). */
export function CloudQuarantine() {
  const [data, setData] = useState<Q | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getCloudQuarantine().then((d) => (setData(d), setError(null)), (e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);
  const live = !!data && (data.sweep.running || data.waiting > 0 || (data.virustotal.queued ?? 0) > 0);
  useEffect(() => { // something is being scanned: keep the numbers current
    if (!live) return;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [live, load]);

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
  const remove = (i: CloudQuarantineItem) => {
    if (window.confirm(`Delete ${i.path} for good?`)) act(async () => `${(await deleteQuarantined(i.id)).path} deleted`);
  };
  const release = (i: CloudQuarantineItem) => {
    if (window.confirm(`Let ${i.path} into the cloud even though it was flagged as "${i.virus}"?\n\n` +
      "Only do this if you are sure it is a false alarm: everyone with Cloud access will be able to download it.")) {
      act(async () => `Released to ${(await releaseQuarantined(i.id)).path}`);
    }
  };
  const scanAll = () => act(async () => `Scanning ${(await scanAllCloudFiles()).queued} existing files in the background`);

  const s = data?.scanner, vt = data?.virustotal;
  return (
    <section className="cloud-log">
      <h2>Cloud virus scanning</h2>
      {note && <p className="ok-note" role="status">{note}</p>}
      {error && <p className="error">{error}</p>}
      {!data ? (
        !error && <Status loading error={null} />
      ) : (
        <>
          <ul className="cloud-av-status">
            <li>
              <strong>ClamAV:</strong>{" "}
              {!s?.enabled ? <span className="muted">off (ECHOVR_CLAMAV not set)</span>
                : s.reachable ? <>running, {s.version} · files up to {s.max_mb} MB are scanned before they can be downloaded</>
                : <span className="error">not reachable: {s.error}</span>}
            </li>
            <li>
              <strong>VirusTotal:</strong>{" "}
              {!vt?.enabled ? <span className="muted">off (ECHOVR_VIRUSTOTAL_KEY not set)</span>
                : !vt.working ? <span className="error">{vt.error}</span>
                : <>fingerprint checks: {vt.today} of {vt.per_day} today, {vt.queued} waiting · {vt.checked} checked
                  ({vt.unknown} unknown to VirusTotal), {vt.found} flagged by {vt.min_engines}+ engines</>}
            </li>
            <li>
              <strong>Waiting for their scan:</strong> {data.waiting}
              {data.scanner_error && <span className="error"> · {data.scanner_error}</span>}
            </li>
            <li>
              {data.sweep.running ? (
                <>Scanning existing files: {data.sweep.done} of {data.sweep.total} · {data.sweep.found} with a virus</>
              ) : (
                <button className="secondary" disabled={busy || (!s?.enabled && !vt?.enabled)} onClick={scanAll}>
                  Scan all existing files
                </button>
              )}
            </li>
          </ul>
          <h3>Quarantine</h3>
          {data.items.length === 0 ? (
            <p className="muted">Nothing in the quarantine.</p>
          ) : (
            <TableWrap>
              <table className="stack">
                <thead>
                  <tr>
                    <th>Found</th>
                    <th>Uploaded by</th>
                    <th>File</th>
                    <th>Found by the scan</th>
                    <th className="num">Size</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.id}>
                      <td data-label="Found" className="nowrap"><LocalTime iso={iso(i.found_at)} /></td>
                      <td data-label="Uploaded by"><span title={i.by_id}>{i.by_name}</span></td>
                      <td data-label="File" className="cloud-name">{i.path}</td>
                      <td data-label="Found by the scan" className="error">{i.virus}</td>
                      <td data-label="Size" className="num">{fileSize(i.size)}</td>
                      <td>
                        <div className="cloud-row-actions">
                          <button disabled={busy} onClick={() => remove(i)}>Delete</button>
                          <button className="link" disabled={busy} onClick={() => release(i)}>Release (false alarm)</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
        </>
      )}
    </section>
  );
}
