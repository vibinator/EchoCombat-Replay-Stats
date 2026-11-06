import { useEffect, useState } from "react";
import { getAvatars } from "../api";

/** Small Discord pictures for a list of players (user, 2026-11-06). One request for the whole list (/api/avatars, never part of the
 *  cached list answers, so a player who switches theirs off disappears at once); players without a visible one get a letter. */
export function useAvatars(ids: string[]): Record<string, string> {
  const key = [...new Set(ids)].sort().slice(0, 100).join(",");
  const [found, setFound] = useState<{ key: string; urls: Record<string, string> }>({ key: "", urls: {} });
  useEffect(() => {
    if (!key) return;
    let live = true;
    getAvatars(key.split(",")).then((urls) => live && setFound({ key, urls }), () => undefined); // pictures are a nicety: never an error
    return () => {
      live = false;
    };
  }, [key]);
  return found.key === key ? found.urls : {};
}

export function Avatar({ name, url, size = 24 }: { name: string; url?: string; size?: number }) {
  const [broken, setBroken] = useState(false);
  const style = { "--avatar": `${size}px` } as React.CSSProperties;
  if (url && !broken)
    return <img className="avatar" style={style} src={url} alt="" width={size} height={size} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />;
  return <span className="avatar placeholder" style={style} aria-hidden="true">{(name.trim()[0] ?? "?").toUpperCase()}</span>;
}
