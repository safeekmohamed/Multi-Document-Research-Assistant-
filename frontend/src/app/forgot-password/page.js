"use client";

import { useState } from "react";
import Link from "next/link";
import { apiRequest } from "../../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [step, setStep] = useState("request");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function requestCode(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const result = await apiRequest("/auth/password/setup/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setMessage(result.message);
      setStep("confirm");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitPasswordSetup(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const result = await apiRequest("/auth/password/setup/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          otp_code: otpCode,
          password,
        }),
      });
      setMessage(result.message);
      setStep("complete");
      setPassword("");
      setConfirmPassword("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-form-card">
        <Link href="/login" className="auth-back-link">
          ← Back to login
        </Link>

        <h1 className="auth-title">Set or reset your password</h1>
        <p className="app-subtitle">
          Verify access to your account email before creating a password.
        </p>

        {message && (
          <div className="mt-5 rounded-xl bg-green-50 p-4 text-sm text-green-700">
            {message}
          </div>
        )}
        {error && (
          <div className="mt-5 rounded-xl bg-red-50 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        {step === "request" && (
          <form onSubmit={requestCode} className="mt-8 space-y-4">
            <label className="sr-only" htmlFor="password-setup-email">
              Email
            </label>
            <input
              id="password-setup-email"
              type="email"
              autoComplete="email"
              placeholder="Email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="auth-input"
            />
            <button
              type="submit"
              disabled={loading}
              className="app-primary-button auth-submit"
            >
              {loading ? "Sending..." : "Email me a verification code"}
            </button>
          </form>
        )}

        {step === "confirm" && (
          <form
            onSubmit={submitPasswordSetup}
            className="mt-8 space-y-4"
          >
            <label className="sr-only" htmlFor="password-setup-otp">
              Email verification code
            </label>
            <input
              id="password-setup-otp"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6-digit verification code"
              value={otpCode}
              onChange={(event) =>
                setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6))
              }
              required
              minLength={6}
              maxLength={6}
              className="auth-input"
            />
            <label className="sr-only" htmlFor="new-password">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              placeholder="New password (at least 6 characters)"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={6}
              maxLength={128}
              className="auth-input"
            />
            <label className="sr-only" htmlFor="confirm-password">
              Confirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              minLength={6}
              maxLength={128}
              className="auth-input"
            />
            <button
              type="submit"
              disabled={loading}
              className="app-primary-button auth-submit"
            >
              {loading ? "Saving..." : "Set password"}
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={requestCode}
              className="w-full text-sm font-semibold text-indigo-600"
            >
              Resend verification code
            </button>
          </form>
        )}

        {step === "complete" && (
          <Link
            href="/login"
            className="app-primary-button auth-submit mt-8 flex items-center justify-center"
          >
            Continue to login
          </Link>
        )}
      </div>
    </main>
  );
}
