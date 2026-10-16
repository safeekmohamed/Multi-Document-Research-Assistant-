"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest } from "../../../../lib/api";
import { saveToken } from "../../../../lib/auth";

export default function GooglePasswordSetupPage() {
  const [setupCode, setSetupCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      const code = fragment.get("setup_code") || "";
      window.history.replaceState(null, "", window.location.pathname);
      setSetupCode(code);
      if (!code) {
        setError(
          "This Google signup session is missing or expired. Please start Google signup again."
        );
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");

    if (!setupCode) {
      setError(
        "This Google signup session is missing or expired. Please start Google signup again."
      );
      return;
    }

    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const result = await apiRequest("/auth/google/password/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          setup_code: setupCode,
          password,
        }),
      });
      saveToken(result.access_token);
      window.location.replace("/dashboard");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-form-card">
        <Link href="/register" className="auth-back-link">
          ← Back to registration
        </Link>

        <h1 className="auth-title">Set your application password</h1>
        <p className="app-subtitle">
          Create a password to use either Google or email sign-in for this
          account.
        </p>

        {error && (
          <div className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="mt-8 space-y-4">
          <label className="sr-only" htmlFor="google-new-password">
            Password
          </label>
          <input
            id="google-new-password"
            type="password"
            autoComplete="new-password"
            placeholder="Password (at least 6 characters)"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={6}
            maxLength={128}
            className="auth-input"
          />
          <label className="sr-only" htmlFor="google-confirm-password">
            Confirm password
          </label>
          <input
            id="google-confirm-password"
            type="password"
            autoComplete="new-password"
            placeholder="Confirm password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={6}
            maxLength={128}
            className="auth-input"
          />
          <button
            type="submit"
            disabled={loading || !setupCode}
            className="app-primary-button auth-submit"
          >
            {loading ? "Setting password..." : "Set Password"}
          </button>
        </form>
      </div>
    </main>
  );
}
