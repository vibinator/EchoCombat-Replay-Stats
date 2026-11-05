import { useCallback, useEffect, useState, type RefObject } from "react";

/** Full screen for one element (the 3D views). Uses the browser's Fullscreen API; where an element cannot go full screen
 *  (iPhone Safari) it fills the page instead (class `pb3d-fake-full`). Escape leaves either way. */
export function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [on, setOn] = useState(false);
  const [fake, setFake] = useState(false);

  useEffect(() => {
    const change = () => setOn(document.fullscreenElement === ref.current);
    document.addEventListener("fullscreenchange", change);
    return () => document.removeEventListener("fullscreenchange", change);
  }, [ref]);

  useEffect(() => {
    if (!fake) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setFake(false); };
    window.addEventListener("keydown", key);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", key); document.body.style.overflow = ""; };
  }, [fake]);

  const toggle = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    if (document.fullscreenElement) { void document.exitFullscreen(); return; }
    if (fake) { setFake(false); return; }
    if (el.requestFullscreen) el.requestFullscreen().catch(() => setFake(true));
    else setFake(true);
  }, [ref, fake]);

  // leaving the page while full screen must not leave the browser in it. The element is kept here because the ref is
  // already empty by the time this cleans up: null === null (nothing full screen) made exitFullscreen() throw.
  useEffect(() => {
    const el = ref.current;
    return () => { if (el && document.fullscreenElement === el) void document.exitFullscreen(); };
  }, [ref]);

  return { full: on || fake, fakeClass: fake ? " pb3d-fake-full" : "", toggle };
}
