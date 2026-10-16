"use client";

import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3">

        <Link
          href="/"
          className="text-lg font-semibold tracking-tight text-slate-900 hover:text-indigo-600"
        >
          Research
          <span className="text-indigo-600">
            AI
          </span>
        </Link>

        <div className="hidden items-center gap-5 md:flex">

          <Link
            href="/dashboard"
            className="text-sm font-medium text-slate-600 transition hover:text-indigo-600"
          >
            Dashboard
          </Link>

          <Link
            href="/documents"
            className="text-sm font-medium text-slate-600 transition hover:text-indigo-600"
          >
            Documents
          </Link>

          <Link
            href="/chat"
            className="text-sm font-medium text-slate-600 transition hover:text-indigo-600"
          >
            Research
          </Link>

          <Link
            href="/history"
            className="text-sm font-medium text-slate-600 transition hover:text-indigo-600"
          >
            History
          </Link>

        </div>

        <Link
          href="/login"
          className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
        >
          Login
        </Link>

      </div>
    </nav>
  );
}
