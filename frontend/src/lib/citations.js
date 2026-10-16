const SOURCE_ID_FIELDS = [
  "source_id",
  "sourceId",
  "document_id",
  "documentId",
  "file_id",
  "fileId",
];

function getText(value) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value).trim();
}

function normalizeUrl(value) {
  const text = getText(value);
  if (!text) {
    return "";
  }

  try {
    const url = new URL(text);
    const pathname = url.pathname.replace(/\/+$/, "");
    return `${url.protocol.toLowerCase()}//${url.host.toLowerCase()}${pathname}${url.search}`;
  } catch {
    return text.replace(/\/+$/, "");
  }
}

export function getCitationIdentity(citation) {
  if (!citation || typeof citation !== "object") {
    return JSON.stringify(["unknown"]);
  }

  for (const field of SOURCE_ID_FIELDS) {
    const id = getText(citation[field]);
    if (id) {
      return JSON.stringify(["id", id]);
    }
  }

  const sourceType = getText(citation.source_type).toLowerCase();
  const url = normalizeUrl(citation.url || citation.source_url);
  if (url) {
    return JSON.stringify(["url", url]);
  }

  const composite = [
    sourceType || "source",
    getText(citation.path || citation.file_path || citation.source_path).toLowerCase(),
    getText(citation.filename || citation.file_name).toLowerCase(),
    getText(citation.source || citation.source_name).toLowerCase(),
    getText(citation.title).toLowerCase(),
    getText(citation.document_type || citation.type).toLowerCase(),
    getText(citation.file_type || citation.extension).toLowerCase(),
  ];

  const hasSourceMetadata = composite.slice(1).some(Boolean);
  return JSON.stringify([
    "composite",
    ...composite,
    hasSourceMetadata ? "" : "unknown source",
  ]);
}

function citationRelevance(citation) {
  const relevance = Number(citation?.relevance);
  if (Number.isFinite(relevance)) {
    return relevance;
  }

  const percentage = Number(citation?.relevance_percentage);
  return Number.isFinite(percentage) ? percentage / 100 : 0;
}

function collectCitationValues(citations, pluralField, singularFields) {
  const values = new Map();

  for (const citation of citations) {
    const pluralValue = citation?.[pluralField];
    const candidates = Array.isArray(pluralValue)
      ? [...pluralValue]
      : pluralValue === null || pluralValue === undefined
        ? []
        : [pluralValue];

    for (const field of singularFields) {
      if (citation?.[field] !== null && citation?.[field] !== undefined) {
        candidates.push(citation[field]);
      }
    }

    for (const value of candidates) {
      const text = getText(value);
      if (text) {
        values.set(text.toLowerCase(), value);
      }
    }
  }

  return [...values.values()];
}

export function deduplicateCitations(citations) {
  if (!Array.isArray(citations)) {
    return [];
  }

  const uniqueCitations = new Map();

  for (const citation of citations) {
    if (!citation || typeof citation !== "object") {
      continue;
    }

    const identity = getCitationIdentity(citation);
    const previous = uniqueCitations.get(identity);
    if (!previous) {
      uniqueCitations.set(identity, {
        ...citation,
        pages: collectCitationValues([citation], "pages", ["page"]),
        snippets: Array.isArray(citation.snippets) ? citation.snippets : [],
        sections: collectCitationValues(
          [citation],
          "sections",
          ["section", "section_title"]
        ),
      });
      continue;
    }

    const preferred =
      citationRelevance(citation) > citationRelevance(previous)
        ? citation
        : previous;
    const other = preferred === citation ? previous : citation;

    uniqueCitations.set(identity, {
      ...other,
      ...preferred,
      pages: collectCitationValues([previous, citation], "pages", ["page"]),
      snippets: [...new Map(
        [...(previous.snippets || []), ...(citation.snippets || [])]
          .filter((snippet) => snippet && typeof snippet === "object")
          .map((snippet) => [
            `${snippet.page || ""}|${snippet.section || ""}|${snippet.text || ""}`.toLowerCase(),
            snippet,
          ])
      ).values()],
      sections: collectCitationValues(
        [previous, citation],
        "sections",
        ["section", "section_title"]
      ),
    });
  }

  return [...uniqueCitations.values()];
}

export function deduplicateSearchedFiles(files) {
  if (!Array.isArray(files)) {
    return [];
  }

  const unique = new Map();
  for (const file of files) {
    if (!file || typeof file !== "object") {
      continue;
    }
    const filename = getText(file.filename || file.title || file.url);
    if (!filename) {
      continue;
    }
    const identity = getText(file.source_id)
      ? `id:${getText(file.source_id)}`
      : getText(file.url)
        ? `url:${normalizeUrl(file.url)}`
        : `name:${filename.toLowerCase()}`;
    if (!unique.has(identity)) {
      unique.set(identity, { ...file, filename });
    }
  }
  return [...unique.values()];
}

export function filterRelevantCitations(citations) {
  return deduplicateCitations(citations).filter((citation) => {
    const hasRelevance = citation.relevance !== null &&
      citation.relevance !== undefined &&
      String(citation.relevance).trim() !== "";
    const relevance = hasRelevance ? Number(citation.relevance) : null;
    const filename = getText(citation.filename);
    const sourceType = getText(citation.source_type).toLowerCase();
    const hasSourceIdentity = Boolean(
      getText(citation.source_id || citation.document_id || citation.url)
    );

    return (
      filename &&
      filename.toLowerCase() !== "no matching source" &&
      ((sourceType === "file" || sourceType === "url") ||
        (!sourceType && hasSourceIdentity)) &&
      (!hasRelevance || (
        Number.isFinite(relevance) &&
        relevance >= 0 &&
        relevance <= 1
      ))
    );
  });
}
