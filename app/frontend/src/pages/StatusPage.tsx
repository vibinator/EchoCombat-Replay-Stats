import { useEffect, useRef, useState } from "react";
import { getMe, getProcessingStatus, loginUrl, type ProcessingStatus } from "../api";
import { BarChart } from "../components/charts";
import { Status, TableWrap } from "../components/common";
import { EmptyState } from "../components/ui";
import { title } from "../format";
import { useApi, useWhileVisible } from "../useApi";

const REFRESH_MS = 10_000;

/** Live progress of replay processing and everything built from it. Admins and console users. */
export function StatusPage() {
  const me = useApi(getMe, "me");
  if (!me.data) return <Status loading={me.loading} error={me.error} />;
  const user = me.data.user;
  if (!user?.admin && !user?.console)
    return (
      <section>
        <h1>Status</h1>
        <EmptyState title="No access">
          {!me.data.enabled ? (
            "Discord login is not set up on this server."
          ) : user ? (
            <>You are logged in as {user.name}, but you do not have access to this page.</>
          ) : (
            <>
              This page is for site staff. <a href={loginUrl("/status")}>Log in with Discord</a>
            </>
          )}
        </EmptyState>
      </section>
    );
  return <ProcessingView />;
}

function useLiveStatus(): { data: ProcessingStatus | null; error: string | null; at: Date | null } {
  const [state, setState] = useState<{ data: ProcessingStatus | null; error: string | null; at: Date | null }>({
    data: null,
    error: null,
    at: null,
  });
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true; // StrictMode mounts twice
    return () => void (mounted.current = false);
  }, []);
  useWhileVisible(() => {
    getProcessingStatus().then(
      (data) => mounted.current && setState({ data, error: null, at: new Date() }),
      (e: Error) => mounted.current && setState((s) => ({ ...s, error: e.message })),
    );
  }, REFRESH_MS); // a hidden tab asks nothing
  return state;
}

const n = (v: number) => v.toLocaleString();

function eta(minutes: number | null): string {
  if (minutes == null) return "–";
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  return h < 48 ? `${h} h ${minutes % 60} min` : `${Math.round(h / 24)} days`;
}

function ago(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  return s < 90 ? `${Math.round(s)} s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}

/** Thin single-series meter: done of total. */
function Meter({ done, total, label }: { done: number; total: number; label: string }) {
  const share = total ? Math.min(1, done / total) : 0;
  return (
    <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
      <div style={{ width: `${share * 100}%` }} />
    </div>
  );
}

function ProcessingView() {
  const { data: d, error, at } = useLiveStatus();
  if (!d) return <Status loading={!error} error={error} />;

  const total = d.counts.queued + d.counts.processing + d.counts.done + d.counts.failed;
  const finished = d.counts.done + d.counts.failed;
  const waiting = d.counts.queued + d.counts.processing;
  const ranking = d.achievement_ranking;

  return (
    <section>
      <div className="section-head">
        <h1>Status</h1>
        <span className="muted">
          {error ? <span className="error">Update failed: {error}</span> : <>Updates every 10 s · last {at?.toLocaleTimeString()}</>}
        </span>
      </div>
      <p className="muted">
        Live progress of reading the replays and everything built from them. Parser version {d.versions.parser}, stats version {d.versions.stats}.
      </p>

      <div className="cards status-tiles">
        <div className="card">
          <span className="muted">Finished</span>
          <strong>{total ? `${((finished / total) * 100).toFixed(1)}%` : "–"}</strong>
          <span className="muted">
            {n(finished)} of {n(total)} replays
          </span>
        </div>
        <div className="card">
          <span className="muted">Waiting</span>
          <strong>{n(waiting)}</strong>
          <span className="muted">{d.redo ? `${n(d.redo)} being redone after an update` : "queued or processing"}</span>
        </div>
        <div className="card">
          <span className="muted">Speed</span>
          <strong>{d.rate_per_min.toLocaleString(undefined, { maximumFractionDigits: 1 })}/min</strong>
          <span className="muted">
            {d.busy} of {d.workers} workers busy
          </span>
        </div>
        <div className="card">
          <span className="muted">Time left</span>
          <strong>{waiting ? eta(d.eta_min) : "Done"}</strong>
          <span className="muted">at the current speed</span>
        </div>
        <div className="card">
          <span className="muted">Failed</span>
          <strong>{n(d.counts.failed)}</strong>
          <span className="muted">{d.hidden_failed ? `${n(d.hidden_failed)} more hidden` : "damaged or not Combat"}</span>
        </div>
      </div>

      <div className="panel">
        <h2>Processing stages</h2>
        <ul className="stage-list">
          {d.stages.map((s) => {
            const complete = s.total != null && s.done >= s.total;
            return (
              <li key={s.key}>
                <div className="stage-head">
                  <strong>{s.label}</strong>
                  <span>
                    {s.total == null ? n(s.done) : `${n(s.done)} / ${n(s.total)}`}
                    {s.total != null && s.total > 0 && <span className="muted"> · {((s.done / s.total) * 100).toFixed(1)}%</span>}
                    {complete && <span className="tag">complete</span>}
                  </span>
                </div>
                {s.total != null && <Meter done={s.done} total={s.total} label={s.label} />}
                <p className="muted">{s.detail}</p>
              </li>
            );
          })}
          <li>
            <div className="stage-head">
              <strong>Achievement leaderboard calculation</strong>
              <span>
                {ranking.calculating
                  ? "Calculating now"
                  : !ranking.calculated
                    ? "Not calculated yet"
                    : ranking.up_to_date
                      ? "Up to date"
                      : "Waiting for new data"}
                {ranking.age_s != null && <span className="muted"> · last {ago(new Date(Date.now() - ranking.age_s * 1000).toISOString())}</span>}
              </span>
            </div>
            <p className="muted">
              Rankings, rarity and recent unlocks for every player. While replays are being read it is recalculated at most every 10 minutes.
            </p>
          </li>
        </ul>
      </div>

      <div className="two-col">
        <div className="panel">
          <h2>Processing now</h2>
          {d.current.length ? (
            <TableWrap>
              <table>
                <thead>
                  <tr>
                    <th>Replay</th>
                    <th className="num">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {d.current.map((c) => (
                    <tr key={c.replay_id}>
                      <td className="path">{c.source_path}</td>
                      <td className="num">{c.seconds.toFixed(0)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          ) : (
            <p className="muted">Nothing right now.</p>
          )}
        </div>
        <div className="panel">
          <h2>Replay folder</h2>
          <dl className="status-facts">
            <dt>Folder</dt>
            <dd>
              <code>{d.source_dir}</code>
            </dd>
            <dt>Reachable</dt>
            <dd>{d.scan.reachable == null ? "Not scanned yet" : d.scan.reachable ? "Yes" : <span className="error">No</span>}</dd>
            <dt>Last scan</dt>
            <dd>
              {d.scan.scanning ? "Scanning now" : ago(d.scan.last_scan_at)}
              {d.scan.last_scan_s != null && !d.scan.scanning && <span className="muted"> · took {d.scan.last_scan_s.toFixed(1)} s</span>}
            </dd>
            <dt>Files</dt>
            <dd>
              {n(d.scan.files)}
              {d.scan.settling > 0 && <span className="muted"> · {n(d.scan.settling)} still being written</span>}
            </dd>
            <dt>Last scan found</dt>
            <dd>
              {n(d.scan.added)} new, {n(d.scan.changed)} changed
            </dd>
            {d.scan.error && (
              <>
                <dt>Error</dt>
                <dd className="error">{d.scan.error}</dd>
              </>
            )}
          </dl>
        </div>
      </div>

      <div className="panel">
        <BarChart
          title="Replays finished per minute, last hour"
          data={d.throughput.map((t) => ({
            label: t.minute.slice(11),
            value: t.replays,
            tooltip: `${t.minute.slice(11)} UTC: ${t.replays} replays`,
          }))}
        />
      </div>

      <div className="two-col">
        <div className="panel">
          <h2>By year recorded</h2>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th className="num">Done</th>
                  <th className="num">Failed</th>
                  <th className="num">Waiting</th>
                  <th>Progress</th>
                </tr>
              </thead>
              <tbody>
                {d.by_year.map((y) => {
                  const all = y.done + y.failed + y.queued + y.processing;
                  return (
                    <tr key={y.year}>
                      <td>{y.year}</td>
                      <td className="num">{n(y.done)}</td>
                      <td className="num">{n(y.failed)}</td>
                      <td className="num">{n(y.queued + y.processing)}</td>
                      <td>
                        <Meter done={y.done + y.failed} total={all} label={`${y.year} finished`} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
        </div>
        <div className="panel">
          <h2>Matches by map</h2>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Map</th>
                  <th className="num">Matches</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(d.matches_by_map)
                  .sort((a, b) => b[1] - a[1])
                  .map(([map, count]) => (
                    <tr key={map}>
                      <td>{title(map)}</td>
                      <td className="num">{n(count)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </TableWrap>
        </div>
      </div>
    </section>
  );
}
