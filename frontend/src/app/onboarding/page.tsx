import { OnboardingForm } from "@/components/onboarding/onboarding-form";

export default function OnboardingPage() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Create your profile</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          The tutor uses this to plan your lessons. You can practice other topics later too.
        </p>
      </header>
      <OnboardingForm />
    </main>
  );
}
