"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAccount } from "@/components/auth/auth-gate";
import { ProfileForm } from "@/components/profile/profile-form";
import { buttonPrimary, errorText, hint } from "@/components/ui";
import { api, type Profile, type ProfileCreate } from "@/lib/api/client";

/** Loads the profile and lets the learner change their main preferences. */
export function ProfileEditor() {
  const { account } = useAccount();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!account.has_profile) return;
    api
      .getProfile()
      .then(setProfile)
      .catch(() => setError("Could not load your profile. Reload the page to try again."));
  }, [account.has_profile]);

  async function save(data: ProfileCreate) {
    setProfile(await api.updateProfile(data));
  }

  if (!account.has_profile) {
    return (
      <div className="flex flex-col items-start gap-4">
        <p className="text-muted">You haven&apos;t set up your profile yet.</p>
        <Link href="/onboarding" className={buttonPrimary}>
          Set up my profile
        </Link>
      </div>
    );
  }
  if (error) return <p className={errorText}>{error}</p>;
  if (!profile) {
    return (
      <p className={hint} role="status">
        Loading your profile…
      </p>
    );
  }
  return (
    <ProfileForm
      // A fresh form for the loaded profile (its fields are initialized once).
      key={profile.id}
      initial={profile}
      submitLabel="Save changes"
      savingLabel="Saving…"
      savedMessage="Saved. The changes apply from your next lesson."
      onSubmit={save}
    />
  );
}
