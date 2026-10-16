"use client";

import { useEffect, useState } from "react";
import { MessageSquareText, Send, X } from "lucide-react";

import { apiRequest } from "../lib/api";

const categories = [
  { value: "bug_report", label: "Bug Report" },
  { value: "suggestion", label: "Suggestion" },
  { value: "general", label: "General Feedback" },
];

export default function FeedbackDialog({ onClose }) {
  const [category, setCategory] = useState("general");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, submitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      setError("Enter a message before submitting.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await apiRequest("/feedback/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, message: trimmedMessage }),
      });
      setSubmitted(true);
    } catch (requestError) {
      setError(requestError?.message || "Unable to submit feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="feedback-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose();
      }}
    >
      <section
        className="feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-dialog-title"
      >
        <header className="feedback-dialog-header">
          <div className="feedback-dialog-title">
            <span className="feedback-dialog-icon"><MessageSquareText size={19} /></span>
            <div>
              <h2 id="feedback-dialog-title">Share feedback</h2>
              <p>Tell us how we can improve your research workspace.</p>
            </div>
          </div>
          <button type="button" className="feedback-dialog-close" onClick={onClose} aria-label="Close feedback">
            <X size={19} />
          </button>
        </header>

        {submitted ? (
          <div className="feedback-dialog-success" role="status">
            <strong>Thank you for your feedback.</strong>
            <span>Your message has been sent to the ResearchAI team.</span>
            <button type="button" className="app-primary-button" onClick={onClose}>Done</button>
          </div>
        ) : (
          <form className="feedback-dialog-form" onSubmit={handleSubmit}>
            <label className="field-label" htmlFor="feedback-category">Category</label>
            <select
              id="feedback-category"
              className="app-select"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              disabled={submitting}
            >
              {categories.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>

            <label className="field-label" htmlFor="feedback-message">Message</label>
            <textarea
              id="feedback-message"
              className="feedback-dialog-textarea"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              maxLength={5000}
              rows={6}
              required
              disabled={submitting}
              placeholder="Describe your feedback…"
            />
            <div className="feedback-dialog-footer">
              <span>{message.length}/5000</span>
              <button type="submit" className="app-primary-button" disabled={submitting || !message.trim()}>
                <Send size={15} />
                {submitting ? "Submitting…" : "Submit feedback"}
              </button>
            </div>
            {error ? <p className="feedback-dialog-error" role="alert">{error}</p> : null}
          </form>
        )}
      </section>
    </div>
  );
}
