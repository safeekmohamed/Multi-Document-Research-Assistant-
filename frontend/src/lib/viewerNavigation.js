const ALLOWED_RETURN_PATHS = ["/documents", "/dashboard", "/chat", "/history"];

function isAllowedPath(pathname) {
  return ALLOWED_RETURN_PATHS.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function getViewerBackDestination({
  search = "",
  referrer = "",
  origin,
  historyLength = 0,
}) {
  let fallback = "/documents";
  try {
    const requested = new URLSearchParams(search).get("returnTo");
    const destination = new URL(requested || fallback, origin);
    if (destination.origin === origin && isAllowedPath(destination.pathname)) {
      fallback = `${destination.pathname}${destination.search}${destination.hash}`;
    }
    const previous = referrer ? new URL(referrer) : null;
    if (
      historyLength > 1 &&
      previous?.origin === origin &&
      isAllowedPath(previous.pathname)
    ) {
      return { useHistory: true, fallback };
    }
  } catch {
    // Invalid or cross-origin values use the safe documents destination.
  }
  return { useHistory: false, fallback };
}
