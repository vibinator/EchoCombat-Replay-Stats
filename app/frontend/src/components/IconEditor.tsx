import { useState } from "react";
import { forgetResponses, getIconChoices, setIcon, uploadIcon, type IconRow } from "../api";
import { useApi } from "../useApi";
import { Status } from "./common";

export const IMG = "/achievements/";
export const GENERIC_ICON = "happy_cubesat.png";

/** Icon picker for one achievement (D43), on the Console page's achievement export. */
export function IconEditor({ row, onDone }: { row: IconRow; onDone: (changed: boolean) => void }) {
  const choices = useApi(getIconChoices, `icon-choices-${row.icon}`); // an upload adds a choice
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function upload(file: File | undefined) {
    if (!file) return;
    if (file.type !== "image/png") return setError("Only PNG files can be used as icons.");
    run(() => uploadIcon(row.id, file));
  }

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
        Current: <img className="icon-thumb" src={IMG + (row.icon ?? GENERIC_ICON)} alt="" /> The change shows on the website straight away.
      </p>
      <label
        className={`upload-drop${dragging ? " dragging" : ""}${busy ? " busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(e.dataTransfer.files?.[0]);
        }}
      >
        <span className="upload-drop-title">{busy ? "Uploading…" : "Upload your own icon"}</span>
        <span className="muted">Click to choose a PNG file, or drop it here. At most 512 KB and 1024 × 1024 pixels.</span>
        <input type="file" accept="image/png" hidden disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
      </label>
      <div className="section-head">
        <h3>Or pick a built-in badge</h3>
        <button className="secondary" disabled={busy || row.icon === row.default_icon} onClick={() => run(() => setIcon(row.id, null))}>
          Reset to original
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
