"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import LoadingSpinner from "../../../../components/LoadingSpinner";
import { saveToken } from "../../../../lib/auth";

export default function GoogleAuthCallbackPage() {
  const [error, setError] = useState("");

  useEffect(() => {
    const fragment = new URLSearchParams(
      window.location.hash.slice(1)
    );
    const token = fragment.get("access_token");
    const setupCode = fragment.get("password_setup_code");
    window.history.replaceState(null, "", window.location.pathname);

    if (setupCode) {
      const destination = new URL(
        "/auth/google/set-password",
        window.location.origin
      );
      destination.hash = new URLSearchParams({
        setup_code: setupCode,
      }).toString();
      window.location.replace(destination.toString());
      return;
    }

    if (!token) {
      const timer = window.setTimeout(() => {
        setError(
          "Google authentication did not return an application session. Please try again."
        );
      }, 0);
      return () => window.clearTimeout(timer);
    }

    saveToken(token);
    window.location.replace("/dashboard");
  }, []);

  return (
    <main className="auth-page">
      <div className="auth-form-card text-center">
        {error ? (
          <>
            <h1 className="auth-title">Google sign-up failed</h1>
            <p className="mt-4 text-sm text-red-600">{error}</p>
            <Link
              className="mt-6 inline-flex font-semibold text-indigo-600"
              href="/register"
            >
              Return to registration
            </Link>
          </>
        ) : (
          <LoadingSpinner text="Finishing secure Google sign-up..." />
        )}
      </div>
    </main>
  );
}
