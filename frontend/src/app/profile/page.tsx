import { AppHeader } from "@/components/brand";
import { ProfileEditor } from "@/components/profile/profile-editor";
import { pageTitle } from "@/components/ui";

export default function ProfilePage() {
  return (
    <>
      <AppHeader />
      {/* Same width as the header, so the content lines up with the logo. */}
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 pb-16 pt-8 sm:px-6 sm:pt-12 [&>*]:max-w-xl">
        <header className="flex flex-col gap-2">
          <h1 className={pageTitle}>Your learning profile</h1>
          <p className="text-[17px] leading-relaxed text-muted">
            The tutor plans every lesson around these settings.
          </p>
        </header>
        <ProfileEditor />
      </main>
    </>
  );
}
