"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest } from "../../lib/api";
import { saveToken } from "../../lib/auth";
import GoogleAuthButton from "../../components/GoogleAuthButton";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const googleError = params.get("google_error");
    if (!googleError) {
      return;
    }

    const errorMessages = {
      not_configured: "Google sign-in is not configured yet.",
      cancelled: "Google sign-in was cancelled.",
      account_not_found:
        "No Google account is registered yet. Create an account first.",
      account_exists:
        "This email belongs to a different sign-in method. Sign in with the existing account; accounts are not linked automatically.",
      account_blocked:
        "This account is blocked. Contact the administrator for help.",
      invalid_state:
        "Google sign-in expired or could not be verified. Please try again.",
      authentication_failed:
        "Google could not verify your sign-in. Please try again.",
    };
    window.history.replaceState(window.history.state, "", "/login");
    const timer = window.setTimeout(() => {
      setError(
        errorMessages[googleError] ||
          "Google sign-in failed. Please try again."
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const data = await apiRequest("/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      saveToken(data.access_token);
      window.location.href = "/dashboard";
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-center">

        <div className="auth-shell">

          <div className="auth-brand">
            <Link href="/" className="text-xl font-bold">
              Research<span className="text-indigo-200">AI</span>
            </Link>

            <div>
              <p className="app-eyebrow">
                Research workspace
              </p>

              <h1 className="auth-brand-title">
                Continue your research journey.
              </h1>

              <p className="auth-brand-copy">
                Access your documents, conversations and
                research tools from one workspace.
              </p>
            </div>
          </div>

          <div className="auth-form-panel">
            <div className="mx-auto max-w-md">

              <Link
                href="/"
                className="text-sm font-medium text-indigo-600"
              >
                ← Back to home
              </Link>

              <h2 className="auth-title">
                Welcome back
              </h2>

              <p className="app-subtitle">
                Sign in to continue your research.
              </p>

              <form
                onSubmit={handleSubmit}
                className="mt-8 space-y-5"
              >
                <input
                  type="email"
                  placeholder="Email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="auth-input"
                />

                <input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="auth-input"
                />

                {error && (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  disabled={loading}
                  className="app-primary-button auth-submit"
                >
                  {loading ? "Signing in..." : "Sign In"}
                </button>
              </form>

              <GoogleAuthButton
                label="Continue with Google"
                intent="login"
              />

              <p className="mt-5 text-center text-sm text-slate-500">
                <Link
                  href="/forgot-password"
                  className="font-semibold text-indigo-600"
                >
                  Set or reset your password
                </Link>
              </p>

              <p className="mt-7 text-center text-sm text-slate-500">
                Don&apos;t have an account?{" "}
                <Link
                  href="/register"
                  className="font-semibold text-indigo-600"
                >
                  Create one
                </Link>
              </p>

            </div>
          </div>

        </div>
      </div>
    </main>
  );
}
