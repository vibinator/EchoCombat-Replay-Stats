import { getMe, loginUrl } from "../api";
import { MegaPrizes } from "../components/AchievementsView";
import { Status } from "../components/common";
import { EmptyState } from "../components/ui";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

/** Draft / beta (user, 2026-11-04): only people with the Preview role. The server checks it too (/api/arena/progress). */
export function MegaPrizesPage() {
  usePageTitle("Mega Prizes");
  const me = useApi(getMe, "me");
  if (!me.data) return <Status loading={me.loading} error={me.error} />;
  const user = me.data.user;
  if (!user?.preview && !user?.console)
    return (
      <section>
        <h1>Mega Prizes</h1>
        <EmptyState title="No access">
          {!me.data.enabled ? (
            "Discord login is not set up on this server."
          ) : user ? (
            <>You are logged in as {user.name}, but you do not have access to this page.</>
          ) : (
            <>
              This page is in preview. <a href={loginUrl("/mega-prizes")}>Log in with Discord</a>
            </>
          )}
        </EmptyState>
      </section>
    );
  return (
    <section>
      <MegaPrizes />
    </section>
  );
}
