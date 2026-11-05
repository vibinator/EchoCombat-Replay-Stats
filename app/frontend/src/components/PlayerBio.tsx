import { useEffect, useState } from "react";
import {
  BIO_MAX,
  getPlayerBio,
  savePlayerBio,
  type PlayerBioProfile,
} from "../api";
import { useApi } from "../useApi";

/** Profile picture beside the player's name: the linked Discord account's avatar, or the avatar of the one Discord
 * member with exactly this name (served by Discord's CDN); nothing when neither, or the player turned it off. */
export function PlayerAvatar({
  profile,
}: {
  profile: PlayerBioProfile | null;
}) {
  if (!profile?.avatar_url) return null;
  return (
    <img
      className="player-avatar"
      src={profile.avatar_url}
      alt=""
      width={64}
      height={64}
      referrerPolicy="no-referrer"
    />
  );
}

/** Loads the Discord-linked profile of a player. `set` replaces it after a save. */
export function usePlayerBio(userId: string) {
  const loaded = useApi(() => getPlayerBio(userId), `bio|${userId}`);
  const [saved, setSaved] = useState<PlayerBioProfile | null>(null);
  useEffect(() => setSaved(null), [userId]);
  return { profile: saved ?? loaded.data, set: setSaved };
}

/** The player's bio, and for the linked Discord account an editor for the only two things they may change: the bio
 * and whether their Discord avatar is shown. */
export function PlayerBio({
  userId,
  profile,
  onSaved,
  save: saveFn,
}: {
  userId?: string;
  profile: PlayerBioProfile | null;
  onSaved: (p: PlayerBioProfile) => void;
  /** another way to save (the logged-in owner's own profile page) */
  save?: (edit: { bio: string | null; show_avatar: boolean }) => Promise<PlayerBioProfile>;
}) {
  const [editing, setEditing] = useState(false);
  const [bio, setBio] = useState("");
  const [showAvatar, setShowAvatar] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!profile?.linked) return null;

  function start() {
    setBio(profile!.bio ?? "");
    setShowAvatar(profile!.show_avatar);
    setError(null);
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const edit = { bio: bio.trim() || null, show_avatar: showAvatar };
      onSaved(await (saveFn ? saveFn(edit) : savePlayerBio(userId!, edit)));
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <div className="player-bio editing">
        <label>
          Profile bio
          <textarea
            value={bio}
            maxLength={BIO_MAX}
            rows={4}
            onChange={(e) => setBio(e.target.value)}
            placeholder="A few words about you"
          />
        </label>
        <span className="muted">
          {bio.length} / {BIO_MAX}
        </span>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showAvatar}
            onChange={(e) => setShowAvatar(e.target.checked)}
          />
          Use my Discord avatar as profile picture
        </label>
        {error && <p className="error">{error}</p>}
        <div className="profile-actions">
          <button onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
          <button
            className="secondary"
            onClick={() => setEditing(false)}
            disabled={busy}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="player-bio">
      {profile.account && (
        <p className="muted" title="Seen on the live Echo match list">
          Linked account: {profile.account.name} · last seen {profile.account.last_seen.slice(0, 10)}
        </p>
      )}
      {profile.bio ? (
        <p>{profile.bio}</p>
      ) : (
        profile.editable && <p className="muted">No bio yet.</p>
      )}
      {profile.editable && (
        <button className="secondary small" onClick={start}>
          Edit profile
        </button>
      )}
    </div>
  );
}
