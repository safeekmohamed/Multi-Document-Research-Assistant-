import { openDocument } from "@/lib/api";

export default function CitationCard({
  citation,
  sourceNumber,
}) {
  const filename =
    citation?.filename ||
    citation?.url ||
    "Unknown source";

  const pages =
    citation?.pages?.length > 0
      ? citation.pages
      : citation?.page !== null && citation?.page !== undefined
        ? [citation.page]
        : [];
  const sections =
    citation?.sections?.length > 0
      ? citation.sections
      : citation?.section || citation?.section_title
        ? [citation.section || citation.section_title]
        : [];
  const match = citation?.relevance_percentage;
  const sourceType = citation?.source_type === "url"
    ? "Website"
    : citation?.source_type === "file"
      ? "File"
      : citation?.type;
  const sourceIdentifier = citation?.document_id || citation?.source_id;
  const snippets = Array.isArray(citation?.snippets)
    ? citation.snippets.filter((snippet) => snippet?.text)
    : [];
  const isMissing = citation?.source_type === "none";

  return (
    <div className="group rounded-lg border border-slate-200 bg-white p-3 transition-colors hover:border-indigo-200 hover:bg-indigo-50/30">

      <div className="flex items-start gap-3">

        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-xs font-bold text-indigo-600">
          {sourceNumber}
        </div>

        <div className="min-w-0">

          <p className="truncate text-sm font-semibold text-slate-800">
            {filename}
          </p>

          {Number.isFinite(match) && (
            <p className="mt-1 text-xs font-medium text-emerald-700">
              {match}% match
            </p>
          )}

          {sourceType && sourceType !== "none" && (
            <p className="mt-1 text-xs capitalize text-slate-500">
              {sourceType}
            </p>
          )}

          {sourceIdentifier && (
            <p
              className="mt-1 max-w-full truncate text-[10px] text-slate-400"
              title={`Source ID: ${sourceIdentifier}`}
            >
              Source ID: {sourceIdentifier}
            </p>
          )}

          {pages.length > 0 && (
            <p className="mt-1 text-xs text-slate-500">
              {pages.length > 1 ? "Pages" : "Page"} {pages.join(", ")}
            </p>
          )}

          {sections.length > 0 && (
            <p className="mt-1 text-xs text-slate-500">
              {sections.length > 1 ? "Sections" : "Section"}{" "}
              {sections.join(", ")}
            </p>
          )}

          {snippets.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {snippets.map((snippet, index) => (
                <li
                  key={`${snippet.page || "page"}-${snippet.section || "section"}-${index}`}
                  className="border-l-2 border-slate-200 pl-2 text-xs leading-5 text-slate-600"
                >
                  {snippet.text}
                  {Number.isFinite(snippet.relevance_percentage) && (
                    <span className="ml-1 whitespace-nowrap font-medium text-emerald-700">
                      {snippet.relevance_percentage}% match
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}

          {citation?.url && (
            <a
              className="mt-1 block truncate text-xs text-indigo-600 hover:underline"
              href={citation.url}
              target="_blank"
              rel="noreferrer"
            >
              Open website source
            </a>
          )}

          {!isMissing &&
            citation?.source_type === "file" &&
            (citation?.document_id || citation?.source_id) && (
            <button
              className="mt-2 text-xs font-semibold text-indigo-600 hover:underline"
              type="button"
              onClick={() =>
                openDocument(
                  citation.document_id || citation.source_id
                )
              }
            >
              View file
            </button>
            )}

        </div>

      </div>

    </div>
  );
}
