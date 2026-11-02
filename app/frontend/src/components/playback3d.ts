// Shared by PlaybackView (main bundle) and Map3D (lazy chunk with three.js): keep three.js imports out of this file.

export type Camera3D = "orbit" | "top" | "follow" | "first";

export const CAMERAS: { value: Camera3D; label: string; help: string }[] = [
  { value: "orbit", label: "Orbit", help: "left-drag turns, right-drag (or Shift + drag) moves sideways, wheel zooms to the pointer, W A S D / Q E fly (Shift = faster), R resets; touch: drag, two fingers, pinch" },
  { value: "top", label: "Top-down", help: "straight down from above (north = -z): drag or W A S D to move, wheel zooms to the pointer, R resets" },
  { value: "follow", label: "Follow player", help: "behind the picked player's head" },
  { value: "first", label: "First person", help: "from the picked player's head (5 samples per second: expect some jumps)" },
];

export function isCamera(v: string | null): v is Camera3D {
  return CAMERAS.some((c) => c.value === v);
}

export const TEAM_COLORS = ["", "#19d9fc", "#ea7924"];
