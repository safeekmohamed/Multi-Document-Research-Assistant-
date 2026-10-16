"use client";

import { useState } from "react";
import { API_BASE_URL } from "../lib/api";

export default function GoogleAuthButton({ label, intent }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function startGoogleAuth() {
    setLoading(true);
    setError("");

    try {
      const googleAuthUrl = new URL("/auth/google", API_BASE_URL);
      googleAuthUrl.searchParams.set("intent", intent);
      if (googleAuthUrl.hostname === "127.0.0.1") {
        googleAuthUrl.hostname = "localhost";
      }
      window.location.assign(googleAuthUrl.toString());
    } catch {
      setLoading(false);
      setError("Unable to start Google sign-in. Please try again.");
    }
  }

  return (
    <div className="auth-google-section">
      <div className="auth-google-divider" aria-hidden="true">
        <span />
        <span>OR</span>
        <span />
      </div>

      {error && (
        <p className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-600">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={loading}
        onClick={startGoogleAuth}
        className="auth-google-button"
      >
        <GoogleMark />
        <span>{loading ? "Redirecting to Google..." : label}</span>
      </button>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 48 48"
      className="auth-google-mark"
    >
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.73 7.18l7.63 5.91c4.45-4.1 7.14-10.14 7.14-17.56z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59a14.4 14.4 0 0 1 0-9.18l-7.98-6.19a23.9 23.9 0 0 0 0 21.56l7.98-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.91-5.89l-7.63-5.91c-2.12 1.42-4.84 2.26-8.28 2.26-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
