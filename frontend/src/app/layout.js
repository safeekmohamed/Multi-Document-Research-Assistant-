import "./globals.css";

export const metadata = {
  title: "ResearchAI",
  description: "Multi-Document AI Research Assistant",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}