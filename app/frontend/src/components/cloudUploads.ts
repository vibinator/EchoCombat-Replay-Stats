// Open Cloud uploads (user, 2026-11-10): many files and whole folders at once, more added while it runs, 3 in parallel.
import { useCallback, useEffect, useReducer, useRef } from "react";
import { makeCloudFolder, uploadCloudFile } from "../api";

/** One file to send, and the folder (relative to the cloud) it goes into. */
export interface Picked {
  file: File;
  dir: string; // "" = the folder the person was in; "Photos/2026" = inside a dropped / chosen folder tree
}

export interface Job extends Picked {
  id: number;
  target: string; // the cloud folder it goes to
  overwrite: boolean;
  sent: number;
  state: "waiting" | "sending" | "done" | "failed" | "skipped";
  error?: string;
}

const PARALLEL = 3; // many small files: round trips overlap; big ones still share the line fairly
const join = (a: string, b: string) => [a, b].filter(Boolean).join("/");

/** Files and folders dropped on the page. The entries must be taken during the drop event itself (the browser empties
 * the list afterwards); reading the folders' contents happens after. Empty folders are listed in `dirs`. */
export function droppedEntries(items: DataTransferItemList): FileSystemEntry[] {
  return Array.from(items)
    .filter((i) => i.kind === "file")
    .map((i) => i.webkitGetAsEntry?.())
    .filter((e): e is FileSystemEntry => !!e);
}

export async function readEntries(entries: FileSystemEntry[]): Promise<{ files: Picked[]; dirs: string[] }> {
  const files: Picked[] = [];
  const dirs: string[] = [];
  async function walk(entry: FileSystemEntry, dir: string): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File>((ok, fail) => (entry as FileSystemFileEntry).file(ok, fail));
      files.push({ file, dir });
    } else if (entry.isDirectory) {
      const path = join(dir, entry.name);
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      let count = 0;
      for (;;) { // readEntries gives at most ~100 at a time: ask until it returns none
        const batch = await new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail));
        if (!batch.length) break;
        count += batch.length;
        for (const child of batch) await walk(child, path);
      }
      if (count === 0) dirs.push(path);
    }
  }
  for (const entry of entries) await walk(entry, "");
  return { files, dirs };
}

/** Files from the "Upload folder" picker: each knows its path inside the chosen folder. */
export function pickedFolder(list: FileList): Picked[] {
  return Array.from(list).map((file) => {
    const rel = file.webkitRelativePath || file.name;
    return { file, dir: rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "" };
  });
}

/** The queue: add() any time; PARALLEL files go at once; onIdle when everything has finished. */
export function useUploadQueue(onIdle: () => void) {
  const jobs = useRef<Job[]>([]);
  const nextId = useRef(1);
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  const frame = useRef(0);
  const idle = useRef(onIdle);
  idle.current = onIdle;

  const draw = useCallback(() => { // progress events come fast: at most one redraw per frame
    if (!frame.current) frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      redraw();
    });
  }, []);

  const pump = useCallback(() => {
    const list = jobs.current;
    while (list.filter((j) => j.state === "sending").length < PARALLEL) {
      const job = list.find((j) => j.state === "waiting");
      if (!job) break;
      job.state = "sending";
      uploadCloudFile(job.target, job.file, job.overwrite, (sent) => {
        job.sent = sent;
        draw();
      }, true).then(
        () => {
          job.sent = job.file.size;
          job.state = "done";
        },
        (e: Error & { status?: number }) => {
          // a file that is already there and the person chose not to replace: skipped, not an error
          job.state = e.status === 409 && !job.overwrite ? "skipped" : "failed";
          job.error = e.message;
        },
      ).finally(() => {
        draw();
        if (!list.some((j) => j.state === "waiting" || j.state === "sending")) idle.current();
        pump();
      });
    }
    draw();
  }, [draw]);

  const add = useCallback((target: string, picked: Picked[], overwrite: boolean) => {
    for (const p of picked) {
      jobs.current.push({ ...p, id: nextId.current++, target: join(target, p.dir), overwrite, sent: 0, state: "waiting" });
    }
    pump();
  }, [pump]);

  /** Empty folders of a dropped tree (files make their own folders on the server). */
  const addFolders = useCallback(async (target: string, dirs: string[]) => {
    for (const dir of dirs) {
      const at = join(target, dir);
      const parent = at.includes("/") ? at.slice(0, at.lastIndexOf("/")) : "";
      await makeCloudFolder(parent, at.slice(at.lastIndexOf("/") + 1), true).catch(() => undefined); // already there: fine
    }
  }, []);

  const retryFailed = useCallback(() => {
    for (const j of jobs.current) if (j.state === "failed") Object.assign(j, { state: "waiting", sent: 0, error: undefined });
    pump();
  }, [pump]);

  const clearFinished = useCallback(() => {
    jobs.current = jobs.current.filter((j) => j.state === "waiting" || j.state === "sending");
    redraw();
  }, []);

  const active = jobs.current.some((j) => j.state === "waiting" || j.state === "sending");
  useEffect(() => { // closing or reloading the tab would stop the uploads: the browser asks first
    if (!active) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);

  return { jobs: jobs.current, active, add, addFolders, retryFailed, clearFinished };
}
