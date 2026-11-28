import { useEffect, useState } from "react";
import {
  BIO_MAX,
  getMe,
  getPlayerBio,
  getPublicBio,
  savePlayerBio,
  type PlayerBioProfile,
  type ProfileEdit,
} from "../api";
import { COUNTRIES, countryName, flagUrl, pickerLabel, regionLabel, regionsFor } from "../regions";
import { useApi } from "../useApi";

/** The flag and game region the player picked, or detected from their connection (user, 2026-11-28), beside their name. */
export function PlayerPlace({ profile }: { profile: PlayerBioProfile | null }) {
  const flag = flagUrl(profile?.country);
  const region = regionLabel(profile?.region);
  if (!flag && !region) return null;
  const where = [profile?.country ? countryName(profile.country) : null, region].filter(Boolean).join(" · ");
  const how = profile?.place_detected ? " (detected from their connection)" : "";
  return (
    <span className="player-place" title={where + how}>
      {flag && <img className="player-flag" src={flag} alt={countryName(profile!.country!)} width={28} height={21} />}
      {region && <span className="player-region">{region}</span>}
      {profile?.place_detected && <span className="muted player-place-detected">detected</span>}
    </span>
  );
}

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
  // not logged in: the shared copy Cloudflare keeps (2026-11-27 review); logged in: the per-visitor one, which says whether
  // this visitor may edit it. Asked once the login state is known, so a logged-in visitor does not ask twice.
  const me = useApi(getMe, "me");
  const known = me.data !== null || me.error !== null;
  const loggedIn = !!me.data?.user;
  const loaded = useApi(() => (!known ? Promise.resolve(null) : loggedIn ? getPlayerBio(userId) : getPublicBio(userId)),
    `bio|${userId}|${known ? loggedIn : "?"}`);
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
  save?: (edit: ProfileEdit) => Promise<PlayerBioProfile>;
}) {
  const [editing, setEditing] = useState(false);
  const [bio, setBio] = useState("");
  const [showAvatar, setShowAvatar] = useState(true);
  const [placeAuto, setPlaceAuto] = useState(true);
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!profile?.linked) return null;

  function start() {
    setBio(profile!.bio ?? "");
    setShowAvatar(profile!.show_avatar);
    setPlaceAuto(profile!.place_auto ?? true);
    setCountry(profile!.country ?? "");
    setRegion(profile!.region ?? "");
    setError(null);
    setEditing(true);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const edit: ProfileEdit = { bio: bio.trim() || null, show_avatar: showAvatar, country: country || null, region: region || null, place_auto: placeAuto };
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
        <fieldset className="profile-place">
          <legend>Flag and region</legend>
          <label className="checkbox">
            <input type="checkbox" checked={placeAuto} onChange={(e) => setPlaceAuto(e.target.checked)} />
            Set them from my connection (shown as "detected"; a VPN shows the VPN's country)
          </label>
          <label>
            Country
            <select value={country} disabled={placeAuto} onChange={(e) => {
              // the region follows the country (user, 2026-11-28): its own one, or East / Central / West to pick from
              const next = e.target.value;
              const allowed = regionsFor(next);
              setCountry(next);
              setRegion(allowed.length === 1 ? allowed[0] : allowed.includes(region) ? region : "");
            }}>
              <option value="">No flag</option>
              {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
          </label>
          <label>
            Game region
            <select value={region} disabled={placeAuto || regionsFor(country).length < 2} onChange={(e) => setRegion(e.target.value)}>
              {regionsFor(country).length !== 1 && <option value="">{country ? "Pick one" : "Pick a country first"}</option>}
              {regionsFor(country).map((key) => <option key={key} value={key}>{pickerLabel(key, country)}</option>)}
            </select>
          </label>
        </fieldset>
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
