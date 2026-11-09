// Shared by PlaybackView (main bundle) and Map3D (lazy chunk with three.js): keep three.js imports out of this file.

export type Camera3D = "orbit" | "top" | "blue" | "orange" | "objective" | "follow" | "first";

export type CameraGroup = "View" | "Ride a player";

export const CAMERAS: { value: Camera3D; label: string; group: CameraGroup; help: string }[] = [
  { value: "orbit", label: "Orbit (overview)", group: "View", help: "left-drag moves sideways, right-drag (or Shift + drag) turns, wheel zooms to the pointer, W A S D / Q E fly (Shift = faster), R resets; touch: drag, two fingers, pinch" },
  { value: "top", label: "Top-down", group: "View", help: "straight down from above (north = -z): drag or W A S D to move, wheel zooms to the pointer, R resets" },
  { value: "blue", label: "Blue end", group: "View", help: "from behind the blue team's start, looking across the arena; every orbit control works from here, R returns" },
  { value: "orange", label: "Orange end", group: "View", help: "from behind the orange team's start, looking across the arena; every orbit control works from here, R returns" },
  { value: "objective", label: "Objective", group: "View", help: "the payload route or the capture point from a few metres above; every orbit control works from here, R returns" },
  { value: "follow", label: "Follow player", group: "Ride a player", help: "behind the picked player's head: drag to swing round them, wheel for distance, R or double-click to put it back" },
  { value: "first", label: "First person", group: "Ride a player", help: "from the picked player's head (5 samples per second: expect some jumps): drag to look around, wheel to zoom, R or double-click to look where they look" },
];

export function isCamera(v: string | null): v is Camera3D {
  return CAMERAS.some((c) => c.value === v);
}

/** Cameras you steer yourself (orbit controls); the others ride along with the picked player. */
export function isFreeCamera(c: Camera3D): boolean {
  return c !== "follow" && c !== "first";
}

/** What the "?" panel lists: [keys / gesture, what it does]. `only` limits a row to some cameras. */
export const CONTROL_HELP: { keys: string; does: string; only?: "free" | "follow" | "first" | "ride" }[] = [
  { keys: "Left-drag", does: "slide the view sideways", only: "free" },
  { keys: "Right-drag / Shift + drag", does: "turn the view around what you look at", only: "free" },
  { keys: "Wheel / pinch", does: "zoom towards the pointer", only: "free" },
  { keys: "W A S D", does: "fly forward, back, left, right", only: "free" },
  { keys: "Q / E", does: "fly down / up", only: "free" },
  { keys: "Shift", does: "hold to fly three times faster", only: "free" },
  { keys: "Drag", does: "swing the camera round the player", only: "follow" },
  { keys: "Wheel", does: "move closer to / further from the player", only: "follow" },
  { keys: "Drag", does: "look around from the player's head", only: "first" },
  { keys: "Wheel", does: "zoom in / out (field of view)", only: "first" },
  { keys: "R / double-click", does: "put the camera back", only: "ride" },
  { keys: "R", does: "put the camera back", only: "free" },
  { keys: "Click a player", does: "pick them" },
  { keys: "1 – 9, 0", does: "pick a player from the roster" },
  { keys: "C", does: "next camera" },
  { keys: "Esc", does: "let go of the picked player" },
  { keys: "Space", does: "play / pause" },
  { keys: "← →", does: "back / forward 5 s (Shift: 30 s)" },
  { keys: ", .", does: "one recorded position back / forward" },
  { keys: "Home / End", does: "start / end of the match" },
  { keys: "[ ]", does: "slower / faster" },
  { keys: "N / P", does: "next / previous fight" },
  { keys: "?", does: "show or hide this list" },
];

export const TEAM_COLORS = ["", "#19d9fc", "#ea7924"];
