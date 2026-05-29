import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata = {
  title: "Sign in · HOSPCALL Backoffice",
};

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <div className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            HOSPCALL
          </div>
          <h1 className="text-xl font-semibold">Backoffice</h1>
          <p className="text-xs text-muted-foreground">
            Sign in to access the operator console.
          </p>
        </div>
        <Suspense>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
