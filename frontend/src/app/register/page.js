"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest, API_BASE_URL } from "../../lib/api";

export default function RegisterPage() {
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
  });

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [googleLoading, setGoogleLoading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const googleError = params.get("google_error");
    if (!googleError) {
      return;
    }

    const errorMessages = {
      not_configured:
        "Google sign-up is not configured yet. Please use email registration or contact the administrator.",
      cancelled: "Google sign-up was cancelled.",
      account_exists:
        "An account already exists for this email. Sign in with that account first; accounts are not linked automatically.",
      account_blocked:
        "This account is blocked. Contact the administrator for help.",
      invalid_state:
        "Google sign-up expired or could not be verified. Please try again.",
      authentication_failed:
        "Google could not verify your sign-in. Please try again.",
    };
    window.history.replaceState(window.history.state, "", "/register");
    const timer = window.setTimeout(() => {
      setError(
        errorMessages[googleError] ||
          "Google sign-up failed. Please try again."
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function change(event) {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    setError("");

    try {
      const data = await apiRequest("/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });

      sessionStorage.setItem(
        "registration_email",
        form.email
      );

      setMessage(data.message);

      setTimeout(() => {
        window.location.href = "/register/verify";
      }, 800);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }

  }

  function startGoogleSignup() {
    setGoogleLoading(true);
    setError("");
    const googleSignupUrl = new URL(
      "/auth/google",
      API_BASE_URL
    );
    googleSignupUrl.searchParams.set("intent", "signup");
    if (googleSignupUrl.hostname === "127.0.0.1") {
      googleSignupUrl.hostname = "localhost";
    }
    window.location.assign(googleSignupUrl.toString());
  }

  return (
    <main className="auth-page">
      <div className="auth-form-card">

        <div>

          <Link
            href="/"
          className="auth-back-link"
          >
            ← Back to home
          </Link>

        <h1 className="auth-title">
            Create your account
          </h1>

        <p className="app-subtitle">
            Start your AI research workspace.
          </p>

        {error && (
          <div className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        <form
            onSubmit={submit}
            className="mt-8 space-y-4"
          >
            <input
              name="name"
              placeholder="Full name"
              value={form.name}
              onChange={change}
              required
              className="auth-input"
            />

            <input
              name="email"
              type="email"
              placeholder="Email"
              value={form.email}
              onChange={change}
              required
              className="auth-input"
            />

            <input
              name="password"
              type="password"
              placeholder="Password"
              value={form.password}
              onChange={change}
              required
              className="auth-input"
            />

            {message && (
              <div className="rounded-xl bg-green-50 p-4 text-sm text-green-600">
                {message}
              </div>
            )}

            <button
              disabled={loading}
              className="app-primary-button auth-submit"
            >
              {loading
                ? "Creating..."
                : "Create Account"}
            </button>
          </form>

          <div className="auth-google-section">
            <div className="auth-google-divider" aria-hidden="true">
                <span />
                <span>OR</span>
                <span />
            </div>

            <button
                type="button"
                disabled={googleLoading}
                onClick={startGoogleSignup}
                className="auth-google-button"
            >
                <GoogleMark />
                <span>
                  {googleLoading
                    ? "Redirecting to Google..."
                    : "Sign up with Google"}
                </span>
            </button>
          </div>

          <p className="mt-6 text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-semibold text-indigo-600"
            >
              Login
            </Link>
          </p>

        </div>
      </div>
    </main>
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
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.73 7.18l7.63 5.91c4.45-4.1 7.14-10.14 7.14-17.56z" />
      <path fill="#FBBC05" d="M10.53 28.59a14.4 14.4 0 0 1 0-9.18l-7.98-6.19a23.9 23.9 0 0 0 0 21.56l7.98-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.91-5.89l-7.63-5.91c-2.12 1.42-4.84 2.26-8.28 2.26-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}
