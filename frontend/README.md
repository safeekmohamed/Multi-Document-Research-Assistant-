This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://github.com/vercel/next.js/tree/canary/packages/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Backend API

The frontend connects to `http://127.0.0.1:8001` by default. To use a backend
at a different address, set `NEXT_PUBLIC_API_BASE_URL` before starting or
building the frontend. Configure the backend's `FRONTEND_ORIGIN` to the
frontend's origin; local `localhost` and `127.0.0.1` origins on the same port
are both supported.

## Google sign-up

Google sign-up uses a backend authorization-code flow. Set these values in
`backend/.env` (never put the client secret in a `NEXT_PUBLIC_*` variable):

```dotenv
GOOGLE_CLIENT_ID=your-web-oauth-client-id
GOOGLE_CLIENT_SECRET=your-web-oauth-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
FRONTEND_ORIGIN=http://localhost:3000
```

In Google Cloud Console, create an OAuth client with application type **Web
application** and add
`http://localhost:8000/auth/google/callback` as an authorized redirect URI.
For a local frontend opened at `http://127.0.0.1:3000`, set
`FRONTEND_ORIGIN` to that origin. This server-side flow does not use a Google
JavaScript SDK, so no authorized JavaScript origin is required. Restart the
backend after changing `backend/.env`. Existing email/password registration and
login remain available.
Google signup asks the user to set an application password after Google
verifies the account. Google login returns existing Google-linked accounts
directly to the dashboard; an email/password account with the same email is
not linked automatically.

## Setting or resetting an account password

Users can set or reset an application password from the Login page. The
backend emails a short-lived, single-use verification code to the account
email before saving a bcrypt password hash. This uses the existing SMTP
configuration (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
and `SMTP_FROM`); no additional OAuth settings are required. Google accounts
can continue using Google sign-in after setting a password.

## User feedback and admin notifications

Authenticated users submit feedback through `POST /feedback/` with a
`category` of `bug_report`, `suggestion`, or `general` and a non-empty
`message` (up to 5,000 characters). The backend derives the submitter's
identity from the authenticated session and stores the feedback, submission
time, and read state in the MongoDB `feedback` collection.

Administrator-only endpoints use the existing admin authorization dependency:

- `GET /admin/feedback` lists feedback (up to 200 records; newest first).
- `GET /admin/feedback/notifications` returns the unread count and up to 10
  unread items for the notification dropdown.
- `PATCH /admin/feedback/{feedback_id}/read` marks a feedback item as read.

The backend creates indexes for submission time and unread-item queries during
its normal database initialization. No feedback processing/status field is
currently implemented.

You can start editing the page by modifying `app/page.js`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
