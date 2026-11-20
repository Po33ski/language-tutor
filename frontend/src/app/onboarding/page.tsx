import { AppHeader } from "@/components/brand";
import { OnboardingForm } from "@/components/onboarding/onboarding-form";
import { pageTitle } from "@/components/ui";

export default function OnboardingPage() {
  return (
    <>
      <AppHeader />
      {/* Same width as the header, so the content lines up with the logo. */}
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 pb-16 pt-8 sm:px-6 sm:pt-12 [&>*]:max-w-xl">
        <header className="flex flex-col gap-2">
          <h1 className={pageTitle}>Create your profile</h1>
          <p className="text-[17px] leading-relaxed text-muted">
            The tutor uses this to plan lessons at your level. You can practice other topics
            later too.
          </p>
        </header>
        <OnboardingForm />
      </main>
    </>
  );
}
