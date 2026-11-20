"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAccount } from "@/components/auth/auth-gate";
import { ProfileForm } from "@/components/profile/profile-form";
import { buttonSecondary, panel } from "@/components/ui";
import { api, type ProfileCreate } from "@/lib/api/client";

export function OnboardingForm() {
  const router = useRouter();
  const { account, refresh } = useAccount();
  // Set once the profile exists, so the form stays up while the page moves home.
  const [created, setCreated] = useState(false);

  async function create(data: ProfileCreate) {
    await api.createProfile(data);
    setCreated(true);
    // The home screen reads `has_profile` from the account: update it before going there.
    await refresh();
    router.push("/");
  }

  if (account.has_profile && !created) {
    return (
      <div className={`${panel} flex flex-col items-start gap-4`}>
        <p>Your profile is already set up.</p>
        <Link href="/" className={buttonSecondary}>
          Go to your lessons
        </Link>
      </div>
    );
  }

  return <ProfileForm submitLabel="Create profile" savingLabel="Saving…" onSubmit={create} />;
}
