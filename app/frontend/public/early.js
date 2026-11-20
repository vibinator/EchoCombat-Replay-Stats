// Starts the data requests a page is certain to make while its code is still downloading (2026-11-16): the answers are
// then waiting when the page asks (api.ts, takeEarly). A plain file, not inline: the site's Content-Security-Policy
// allows no inline scripts. The addresses must be exactly the ones api.ts builds; one that is never asked for is only
// a wasted request. Nothing is started when this tab already holds saved answers (a reload shows those at once).
(function () {
  // the opened page's own code (a few KB), asked for now instead of once the main script has run. The list of files per
  // page is written into index.html by the build (vite.config.ts, pageFiles); the addresses mirror the routes in App.tsx
  try {
    var route = location.pathname, page =
      route === "/matches" ? "MatchesPage" : /^\/matches\/./.test(route) ? "MatchPage" :
      route === "/players" ? "PlayersPage" : /^\/players\/./.test(route) ? "PlayerPage" :
      route === "/leaderboard" ? "LeaderboardPage" : /^\/(challenges?|achievements)(\/|$)/.test(route) ? "AchievementsPage" :
      /^\/combat\/./.test(route) ? "CombatPage" : route === "/console" ? "ConsolePage" : route === "/cloud" ? "CloudPage" :
      route === "/profile" ? "ProfilePage" : route === "/permissions" ? "PermissionsPage" : "";
    var list = document.getElementById("page-files");
    ((page && list && JSON.parse(list.textContent)[page]) || []).forEach(function (href) {
      var link = document.createElement("link");
      link.rel = "modulepreload";
      link.crossOrigin = "";
      link.href = href;
      document.head.appendChild(link);
    });
  } catch (e) {
    /* the page loads its code the usual way */
  }
  try {
    for (var i = 0; i < sessionStorage.length; i++) if ((sessionStorage.key(i) || "").indexOf("echovr:") === 0) return;
  } catch (e) {
    /* no storage: go on */
  }
  var path = location.pathname, plain = !location.search, m;
  var paths = ["/api/auth/me", "/api/challenges", "/api/health", "/api/overview/processing"];
  if (path === "/") {
    paths.push("/api/overview", "/api/overview/latest", "/api/overview/activity?bucket=day", "/api/overview/players-seen?range=7d&anchor=now");
  } else if (path === "/matches" && plain) {
    paths.push("/api/matches/summary", "/api/matches?with_players=true&limit=24&offset=0");
  } else if ((m = /^\/matches\/(\d+)$/.exec(path))) {
    paths.push("/api/matches/" + m[1]);
  } else if ((m = /^\/players\/(?:[^/]+\/)?(\d+)$/.exec(path)) && !/[?&](period|map)=/.test(location.search)) {
    paths.push("/api/players/" + m[1] + "?period=all", "/api/players/" + m[1] + "/trends?bucket=month", "/api/combat/players/" + m[1] + "?period=all");
  } else if (path === "/leaderboard" && plain) {
    paths.push("/api/leaderboard/overview?period=all&min_games=10", "/api/leaderboard/stats");
  }
  // an admin asks for their own version of the answers with hidden stats (api.ts forViewer, same pattern and cookie)
  var admin = /(?:^|;\s*)echovr_admin=1(?:;|$)/.test(document.cookie);
  var view = /^\/api\/(overview|leaderboard(\/stats|\/overview)?|players\/compare\/[^/?]+|players\/[^/?]+(\/trends|\/companions)?)(\?|$)/;
  paths = paths.map(function (p) {
    return admin && view.test(p) ? p + (p.indexOf("?") < 0 ? "?" : "&") + "view=admin" : p;
  });
  var early = (window.__early = {});
  paths.forEach(function (p) {
    early[p] = fetch(p, { headers: { "X-EchoVR": "1" } });
    early[p].catch(function () {});
  });
})();
