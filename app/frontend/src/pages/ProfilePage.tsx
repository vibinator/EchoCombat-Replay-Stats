import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getMyProfile, loginUrl, saveMyProfile, type MyProfile } from "../api";
import { PlayerAvatar, PlayerBio } from "../components/PlayerBio";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

/** My profile (user, 2026-11-05): the logged-in Discord account's bio pane. Editable only by that account (the server
 * checks the login, not this page); the Discord id comes from the Echo match list, so anyone who has played has one. */
export function ProfilePage() {
  usePageTitle("My profile");
  const loaded = useApi(getMyProfile, "my-profile");
  const [saved, setSaved] = useState<MyProfile | null>(null);
  useEffect(() => setSaved(null), [loaded.data]);
  const profile = saved ?? loaded.data;

  if (loaded.error && !profile) {
    return (
      <section>
        <h1>My profile</h1>
        <p>Log in with Discord to see and edit your profile.</p>
        <p>
          <a className="button" href={loginUrl("/profile")}>Log in with Discord</a>
        </p>
      </section>
    );
  }
  if (!profile) return <section><h1>My profile</h1><p className="muted">Loading…</p></section>;
  return (
    <section>
      <div className="profile-identity">
        <PlayerAvatar profile={profile} />
        <h1>{profile.name}</h1>
      </div>
      {profile.known ? (
        <>
          <PlayerBio
            profile={{ ...profile, linked: true, editable: true }}
            onSaved={(p) => setSaved({ ...profile, ...p })}
            save={(edit) => saveMyProfile(edit)}
          />
          {profile.user_id && (
            <p>
              <Link to={`/players/${profile.user_id}`}>Your player page and stats</Link>
            </p>
          )}
        </>
      ) : (
        <p className="muted">
          Your Discord account has not been seen on the Echo match list yet. Play a match, then come back to write your bio. If you
          already have stats here under another account, ask an admin to link them.
        </p>
      )}
    </section>
  );
}
