import { getChallenges, type AchievementPeek } from "./api";
import { useApi } from "./useApi";

/** Small summary for the player page; the full list lives on /challenges. */
export interface AchievementsAccess {
  /** this visitor sees achievements: launched, or a Discord preview (null while loading) */
  visible: boolean | null;
  launched: boolean;
  preview: boolean;
  start: string | null;
  /** number of achievements available (null while loading) */
  total: number | null;
  peek: AchievementPeek | null;
}

export function useAchievementsAccess(): AchievementsAccess {
  const d = useApi(getChallenges, "challenge").data;
  return {
    visible: d ? d.launched || d.preview : null,
    launched: !!d?.launched,
    preview: !!d?.preview,
    start: d?.start ?? null,
    total: d?.total ?? null,
    peek: d?.peek ?? null,
  };
}
