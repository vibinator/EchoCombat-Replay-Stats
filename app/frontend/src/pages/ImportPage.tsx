import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { getImportStatus, listReplays, type ImportStage, type ImportStatus, type Replay } from "../api";
import { BarChart } from "../components/charts";
import { Status, TableWrap } from "../components/common";
import { dateTime, title } from "../format";

const POLL_MS = 5000;

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

function eta(minutes: number | null): string {
  if (minutes == null) return "–";
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function StageRow({ stage }: { stage: ImportStage }) {
  const share = stage.total ? Math.min(1, stage.done / stage.total) : null;
  return (
    <li className="stage">
      <div className="stage-head">
        <strong>{stage.label}</strong>
        <span className="num">
          {stage.done.toLocaleString()}
          {stage.total != null && <span className="muted"> / {stage.total.toLocaleString()}</span>}
        </span>
      </div>
      {share != null && (
        <div className="bar" role="progressbar" aria-valuenow={Math.round(share * 100)} aria-label={stage.label}>
          <div style={{ width: `${share * 100}%` }} />
        </div>
      )}
      <p className="muted">{stage.detail}</p>
    </li>
  );
}

const REPAIRABLE = new Set(["corrupt", "incomplete", "internal", "crashed"]);

function ReplayTable({ replays, showError }: { replays: Replay[]; showError?: boolean }) {
  return (
    <TableWrap>
      <table className="stack">
        <thead>
          <tr>
            <th>File</th>
            <th className="num">Size</th>
            <th>{showError ? "Reason" : "Processed (UTC)"}</th>
            {showError && <th>Repair</th>}
          </tr>
        </thead>
        <tbody>
          {replays.map((r) => (
            <tr key={r.id}>
              <td className="path" data-label="File">
                {r.match_id ? <Link to={`/matches/${r.match_id}`}>{r.source_path}</Link> : r.source_path}
                {r.repair_requested && r.status === "done" && <span className="tag">repaired</span>}
                {r.warnings.length > 0 && (
                  <span className="tag" title={r.warnings.join("\n")}>
                    {r.warnings.length} warning{r.warnings.length > 1 ? "s" : ""}
                  </span>
                )}
              </td>
              <td className="num">{formatSize(r.size_bytes)}</td>
              <td>{showError ? r.error_message?.split("\n")[0] : r.processed_at && dateTime(r.processed_at)}</td>
              {showError && (
                <td data-label="Repair" className="muted">
                  {r.error_code && REPAIRABLE.has(r.error_code)
                    ? r.repair_requested ? "repair tried, still failing" : "repairable (admin console)"
                    : r.error_code === "unsupported" ? "not an Echo Combat replay" : "not repairable"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export function ImportPage() {
  const [status, setStatus] = useState<ImportStatus | null>(null);
  const [failed, setFailed] = useState<Replay[]>([]);
  const [recent, setRecent] = useState<Replay[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, f, d] = await Promise.all([getImportStatus(), listReplays("failed", 50), listReplays("done", 10)]);
      setStatus(s);
      setFailed(f.items);
      setRecent(d.items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const c = status?.counts;
  const scan = status?.scan;
  const waiting = c ? c.queued + c.processing : 0;

  return (
    <section>
      <h1>Import</h1>
      <p className="muted">
        Replays are read automatically from the replay folder (read-only), newest first. New files are picked up every few
        minutes; finished replays are never read again unless they change or the app is updated.
      </p>
      <Status loading={!status && !error} error={error} />

      {status && c && scan && (
        <>
          <div className="cards">
            <div className="card">
              <span className="label">Waiting</span>
              <strong>{waiting.toLocaleString()}</strong>
            </div>
            <div className="card">
              <span className="label">Speed</span>
              <strong>{status.rate_per_min.toLocaleString()} / min</strong>
            </div>
            <div className="card">
              <span className="label">Time left</span>
              <strong>{waiting ? eta(status.eta_min) : "Up to date"}</strong>
            </div>
            <div className="card">
              <span className="label">Workers busy</span>
              <strong>
                {status.busy} / {status.workers}
              </strong>
            </div>
          </div>

          {status.redo > 0 && (
            <p className="note">
              {status.redo.toLocaleString()} replays are being reprocessed after an app update (parser v{status.versions.parser},
              stats v{status.versions.stats}). Their previous results stay visible until each one is replaced.
            </p>
          )}

          <p className={scan.reachable === false ? "error" : "muted"}>
            Folder: <code>{status.source_dir}</code>
            {" · "}
            {scan.scanning
              ? "scanning now…"
              : scan.reachable === false
                ? scan.error
                : scan.last_scan_at
                  ? `last scan ${dateTime(scan.last_scan_at)} UTC: ${scan.files.toLocaleString()} files (${scan.added} new, ${scan.changed} changed) in ${scan.last_scan_s}s`
                  : "first scan pending"}
            {scan.settling > 0 && ` · ${scan.settling} still being written`}
          </p>

          <h2>What each replay produces</h2>
          <ol className="stages">
            {status.stages.map((s) => (
              <StageRow key={s.key} stage={s} />
            ))}
          </ol>
          {Object.keys(status.matches_by_map).length > 0 && (
            <p className="muted">
              Matches per map:{" "}
              {Object.entries(status.matches_by_map)
                .map(([m, n]) => `${title(m)} ${n.toLocaleString()}`)
                .join(" · ")}
            </p>
          )}

          <div className="two-col">
            <BarChart
              title="Replays finished per minute (last hour)"
              unit=" replays"
              data={status.throughput.map((m) => ({ label: m.minute.slice(11), value: m.replays, tooltip: `${m.minute.slice(11)} UTC` }))}
            />
            <div>
              <h3>Archive progress by year</h3>
              <TableWrap>
                <table className="stack">
                  <thead>
                    <tr><th>Year</th><th className="num">Done</th><th className="num">Waiting</th><th className="num">Failed</th><th>Progress</th></tr>
                  </thead>
                  <tbody>
                    {status.by_year.map((y) => {
                      const total = y.done + y.failed + y.queued + y.processing;
                      return (
                        <tr key={y.year}>
                          <td data-label="Year">{y.year}</td>
                          <td data-label="Done" className="num">{y.done.toLocaleString()}</td>
                          <td data-label="Waiting" className="num">{(y.queued + y.processing).toLocaleString()}</td>
                          <td data-label="Failed" className="num">{y.failed.toLocaleString()}</td>
                          <td data-label="Progress">
                            <div className="bar"><div style={{ width: `${total ? ((y.done + y.failed) / total) * 100 : 0}%` }} /></div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          </div>

          <h2>Processing now</h2>
          {status.current.length === 0 ? (
            <p className="muted">Idle.</p>
          ) : (
            <TableWrap>
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th className="num">Running for</th>
                  </tr>
                </thead>
                <tbody>
                  {status.current.map((f) => (
                    <tr key={f.replay_id}>
                      <td className="path">{f.source_path}</td>
                      <td className="num">{f.seconds.toFixed(0)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}

          {failed.length > 0 && (
            <>
              <h2>Failed ({c.failed.toLocaleString()})</h2>
              <p className="muted">
                Damaged files can be repaired in the admin console (<code>admin.bat repair-failed</code>): repair re-reads a file in salvage mode and
                keeps every readable part. The original file is never changed. Repaired matches are marked "repaired".
              </p>
              <ReplayTable replays={failed} showError />
              {c.failed > failed.length && <p className="muted">Showing the {failed.length} newest.</p>}
            </>
          )}
          {status.hidden_failed > 0 && (
            <p className="muted">{status.hidden_failed.toLocaleString()} failed replays that cannot be repaired are hidden (admin console).</p>
          )}

          <h2>Recently processed</h2>
          {recent.length === 0 ? <p className="muted">Nothing processed yet.</p> : <ReplayTable replays={recent} />}
        </>
      )}
    </section>
  );
}
