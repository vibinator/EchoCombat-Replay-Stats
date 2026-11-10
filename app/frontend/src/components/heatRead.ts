import type { MapHeat } from "../api";
import { pct } from "../format";

/** The palette entry of every pixel of a map heat PNG (map_heat.py draws 8-bit palette PNGs, rows unfiltered). The
 * entry is the value: the read-out under the pointer needs no second request and no guessing from colours. */
export interface Entries {
  width: number;
  height: number;
  data: Uint8Array; // row by row, 0 = clear
}

export async function decodeEntries(dataUrl: string): Promise<Entries | null> {
  try {
    const bin = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
    const png = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) png[i] = bin.charCodeAt(i);
    const view = new DataView(png.buffer);
    let width = 0;
    let height = 0;
    const idat: Uint8Array[] = [];
    for (let at = 8; at + 8 <= png.length; ) {
      const length = view.getUint32(at);
      const kind = bin.slice(at + 4, at + 8);
      if (kind === "IHDR") {
        width = view.getUint32(at + 8);
        height = view.getUint32(at + 12);
        if (png[at + 16] !== 8 || png[at + 17] !== 3) return null; // not an 8-bit palette picture
      } else if (kind === "IDAT") idat.push(png.subarray(at + 8, at + 8 + length));
      at += 12 + length;
    }
    if (!width || !height || !idat.length || typeof DecompressionStream === "undefined") return null;
    const stream = new Blob(idat as BlobPart[]).stream().pipeThrough(new DecompressionStream("deflate"));
    const raw = new Uint8Array(await new Response(stream).arrayBuffer());
    if (raw.length !== height * (width + 1)) return null;
    const data = new Uint8Array(width * height);
    for (let row = 0; row < height; row++) {
      if (raw[row * (width + 1)] !== 0) return null; // a filtered row: not ours
      data.set(raw.subarray(row * (width + 1) + 1, (row + 1) * (width + 1)), row * width);
    }
    return { width, height, data };
  } catch {
    return null;
  }
}

/** The entry at a point of the picture (fractions 0-1 from its top left). */
export function entryAt(entries: Entries, fx: number, fy: number): number {
  if (fx < 0 || fy < 0 || fx >= 1 || fy >= 1) return 0;
  return entries.data[Math.floor(fy * entries.height) * entries.width + Math.floor(fx * entries.width)];
}

const times = (v: number) => `${v >= 10 ? v.toFixed(0) : v.toFixed(1)}×`;

/** What a palette entry says, in words (map_heat.READ). `one` / `other`: the names of the chosen layer and, when two
 * are compared, of the other one. null = nothing to say here (a clear pixel). */
export function readOut(heat: MapHeat, map: string, entry: number, one: string, other: string): string | null {
  const read = heat.read;
  if (!entry || !read) return null;
  const steps = read.steps ?? 1;
  const level = steps > 1 ? ((entry - 1) % steps) / (steps - 1) : 0;
  const top = level >= 1;
  if (heat.view === "favoured") {
    const from = read.from ?? 1;
    const value = from + level * ((heat.maps[map]?.top ?? from) - from);
    const what = heat.layer.startsWith("death:") ? "as many deaths as the time spent here suggests" : "as often as usual";
    return `${one}: ${times(value)} ${what}${top ? " or more" : ""}`;
  }
  if (heat.view === "compare") {
    const from = read.from ?? 0;
    const lean = Math.min(0.49, from + level * ((heat.maps[map]?.top ?? from) - from));
    const first = entry <= steps;
    return `${first ? one : other}: ${times((0.5 + lean) / (0.5 - lean))} as often here as ${first ? other : one}${top ? " or more" : ""}`;
  }
  if (heat.view === "all") return `${one}: ${top ? "among the busiest spots" : `${pct(level * level)} of the busiest spots`}`;
  if (heat.view === "payload" && heat.scale) {
    const value = heat.scale.min + level * (heat.scale.max - heat.scale.min);
    const edge = top ? " or more" : level <= 0 ? " or less" : "";
    if (heat.layer === "payload:back") return `Payload: rolling back ${pct(value)} of the time${edge}`;
    return `Payload: ${value.toFixed(2)} m/s on average${heat.layer === "payload:moving" ? " while moving forward" : ""}${edge}`;
  }
  if (heat.view === "teams" && read.alpha_steps && read.share_steps && read.contrast) {
    const step = Math.floor((entry - 1) / read.alpha_steps);
    const orange = 0.5 + (step / (read.share_steps - 1) - 0.5) / read.contrast;
    if (step === 0) return `Blue ${pct(1 - orange)} or more of the time here`;
    if (step === read.share_steps - 1) return `Orange ${pct(orange)} or more of the time here`;
    return `Blue ${pct(1 - orange)} · Orange ${pct(orange)} of the time here`;
  }
  return null;
}
