"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "../../../lib/api";
import Link from "next/link";

export default function VerifyPage() {
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const savedEmail =
      sessionStorage.getItem(
        "registration_email"
      );

    if (savedEmail) {
      setEmail(savedEmail);
    }
  }, []);

  async function verify(event) {
    event.preventDefault();

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const data = await apiRequest(
        "/auth/verify-otp",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
            otp_code: otp,
          }),
        }
      );

      setMessage(data.message);

      sessionStorage.removeItem(
        "registration_email"
      );

      setTimeout(() => {
        window.location.href = "/login";
      }, 1000);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function resend() {
    setError("");
    setMessage("");

    try {
      const data = await apiRequest(
        "/auth/resend-otp",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
          }),
        }
      );

      setMessage(data.message);
    } catch (error) {
      setError(error.message);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-form-card">

        <div>

          <Link
            href="/register"
            className="auth-back-link"
          >
            ← Back
          </Link>

          <h1 className="auth-title">
            Verify your email
          </h1>

          <p className="app-subtitle">
            Enter the OTP sent to your email.
          </p>

          <form
            onSubmit={verify}
            className="mt-8 space-y-4"
          >
            <input
              type="email"
              value={email}
              onChange={(e) =>
                setEmail(e.target.value)
              }
              placeholder="Email"
              required
              className="auth-input"
            />

            <input
              inputMode="numeric"
              maxLength={6}
              value={otp}
              onChange={(e) =>
                setOtp(e.target.value.replace(/\D/g, ""))
              }
              placeholder="6-digit OTP"
              required
              className="auth-input otp-input"
            />

            {error && (
              <div className="rounded-xl bg-red-50 p-4 text-sm text-red-600">
                {error}
              </div>
            )}

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
                ? "Verifying..."
                : "Verify Email"}
            </button>
          </form>

          <button
            onClick={resend}
            className="mt-5 w-full text-sm font-semibold text-indigo-600 hover:text-indigo-700"
          >
            Resend OTP
          </button>

        </div>
      </div>
    </main>
  );
}
