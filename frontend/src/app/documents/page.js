"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../../components/Sidebar";
import UploadBox from "../../components/UploadBox";
import DocumentCard from "../../components/DocumentCard";

import {
  Search,
  Upload,
  FileText,
  Globe2,
  FileStack,
  Plus,
} from "lucide-react";

import {
  apiRequest,
  getDocuments,
} from "../../lib/api";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [deletingId, setDeletingId] = useState(null);

  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");

  const [selectedId, setSelectedId] = useState("");

  const [urlLoading, setUrlLoading] = useState(false);
  const [url, setUrl] = useState("");

  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

async function loadAllSources() {
    setListLoading(true);

    try {
      const documentData = await getDocuments();

      if (!Array.isArray(documentData?.documents)) {
        throw new Error(
          "Unexpected documents response."
        );
      }

      setDocuments(documentData.documents);
      setListError("");
    } catch (error) {
      console.error(error);

      setListError(
        error?.message || "Unable to load sources."
      );
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    loadAllSources();
  }, []);

useEffect(() => {
    setSelectedId(
      new URLSearchParams(
        window.location.search
      ).get("selected") || ""
    );
  }, []);

  useEffect(() => {
    if (!selectedId || !documents.length) {
      return;
    }

    const selected = documents.find(
      (item) =>
        String(item.id || item._id) ===
        selectedId
    );

    if (selected) {
      document
        .getElementById(
          `source-${selectedId}`
        )
        ?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
    }
  }, [selectedId, documents]);

async function handleFilesSelected(files) {
    if (!files?.length) {
      return;
    }

    setLoading(true);
    setError("");
    setNotice("");

    try {
      const formData = new FormData();

      files.forEach((file) => {
        formData.append("files", file);
      });

      await apiRequest(
        "/documents/upload",
        {
          method: "POST",
          body: formData,
        }
      );

      await loadAllSources();

      window.dispatchEvent(
        new Event(
          "research:sources-updated"
        )
      );

      setNotice(
        "Documents uploaded successfully."
      );

      window.setTimeout(() => {
        setNotice("");
      }, 3500);
    } catch (error) {
      console.error(error);

      setError(
        error.message ||
          "Document upload failed."
      );
    } finally {
      setLoading(false);
    }
  }

async function handleDelete(document) {
    const documentId =
      document?.id || document?._id;

    if (!documentId) {
      return;
    }

    const confirmed = window.confirm(
      `Are you sure you want to delete "${
        document.filename ||
        document.title ||
        document.source_url ||
        "this source"
      }"?`
    );

    if (!confirmed) {
      return;
    }

    setDeletingId(documentId);
    setError("");
    setNotice("");

    try {
      await apiRequest(
        `/documents/${documentId}`,
        {
          method: "DELETE",
        }
      );

      await loadAllSources();

      window.dispatchEvent(
        new Event(
          "research:sources-updated"
        )
      );

      setNotice(
        "Source deleted successfully."
      );

      window.setTimeout(() => {
        setNotice("");
      }, 3500);
    } catch (error) {
      console.error(error);

      setError(
        error.message ||
          "Failed to delete source."
      );
    } finally {
      setDeletingId(null);
    }
  }

async function handleAddUrl(event) {
    event.preventDefault();

    const cleanUrl = url.trim();

    if (!cleanUrl) {
      setError(
        "Please enter a website URL."
      );

      return;
    }

    setUrlLoading(true);
    setError("");
    setNotice("");

    try {
      await apiRequest(
        "/urls/add",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            url: cleanUrl,
          }),
        }
      );

      setUrl("");

      await loadAllSources();

      window.dispatchEvent(
        new Event(
          "research:sources-updated"
        )
      );

      setNotice(
        "Website added successfully."
      );

      window.setTimeout(() => {
        setNotice("");
      }, 3500);
    } catch (error) {
      console.error(error);

      setError(
        error.message ||
          "Failed to add URL."
      );
    } finally {
      setUrlLoading(false);
    }
  }

const filteredDocuments = useMemo(() => {
    const cleanSearch =
      search.trim().toLowerCase();

    return documents.filter(
      (document) => {
        const filename =
          document?.filename
            ?.toLowerCase() || "";

        const sourceUrl =
          document?.source_url
            ?.toLowerCase() || "";

        const urlValue =
          document?.url
            ?.toLowerCase() || "";

        const sourceType =
          document?.source_type
            ?.toLowerCase() || "";

        const fileType =
          document?.file_type
            ?.toLowerCase() || "";

        const matchesSearch =
          !cleanSearch ||
          filename.includes(
            cleanSearch
          ) ||
          sourceUrl.includes(
            cleanSearch
          ) ||
          urlValue.includes(
            cleanSearch
          ) ||
          sourceType.includes(
            cleanSearch
          ) ||
          fileType.includes(
            cleanSearch
          );

        const normalizedType =
          fileType.toUpperCase();

        const matchesType =
          activeFilter === "All" ||
          (
            activeFilter === "Web"
              ? sourceType === "url"
              : sourceType !== "url" &&
                normalizedType ===
                  activeFilter
          );

        return (
          matchesSearch &&
          matchesType
        );
      }
    );
  }, [
    documents,
    search,
    activeFilter,
  ]);

const countFileType = (type) =>
    documents.filter(
      (item) =>
        item?.source_type !== "url" &&
        String(
          item?.file_type || ""
        ).toLowerCase() === type
    ).length;

  const pdfCount =
    countFileType("pdf");

  const docxCount =
    countFileType("docx");

  const txtCount =
    countFileType("txt");

  const otherCount = Math.max(
    0,
    documents.length -
      pdfCount -
      docxCount -
      txtCount
  );

  const filters = [
    "All",
    "PDF",
    "DOCX",
    "TXT",
    "CSV",
    "XLSX",
    "PPTX",
    "Web",
  ];

function formatAddedDate(value) {
    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return "—";
    }

    return date.toLocaleDateString(
      undefined,
      {
        month: "short",
        day: "numeric",
        year: "numeric",
      }
    );
  }

return (
    <AppShell
      className="documents-page"
      contentClassName="app-content documents-content"
    >
      { }

      <header className="documents-page-heading">
        <div>
          <p className="app-eyebrow">
            Research Workspace
          </p>

          <h1 className="app-title">
            Documents
          </h1>

          <p className="app-subtitle">
            Manage your uploaded files
            and saved sources.
          </p>
        </div>
      </header>

      { }

      <section
        className="documents-summary"
        aria-label="Document summary"
      >
        <article className="documents-summary-card">
          <span className="documents-summary-icon blue">
            <FileStack size={17} />
          </span>

          <div>
            <strong>
              {documents.length}
            </strong>

            <span>
              Total Sources
            </span>
          </div>
        </article>

        <article className="documents-summary-card">
          <span className="documents-summary-icon red">
            <FileText size={17} />
          </span>

          <div>
            <strong>
              {pdfCount}
            </strong>

            <span>PDF</span>
          </div>
        </article>

        <article className="documents-summary-card">
          <span className="documents-summary-icon slate">
            <FileText size={17} />
          </span>

          <div>
            <strong>
              {docxCount}
            </strong>

            <span>DOCX</span>
          </div>
        </article>

        <article className="documents-summary-card">
          <span className="documents-summary-icon amber">
            <FileText size={17} />
          </span>

          <div>
            <strong>
              {txtCount}
            </strong>

            <span>TXT</span>
          </div>
        </article>

        <article className="documents-summary-card">
          <span className="documents-summary-icon green">
            <Globe2 size={17} />
          </span>

          <div>
            <strong>
              {otherCount}
            </strong>

            <span>Other</span>
          </div>
        </article>
      </section>

      { }

      <section
        className="documents-upload-panel"
        id="upload-section"
      >
        <div className="documents-upload-copy">
          <span className="documents-upload-icon">
            <Upload size={18} />
          </span>

          <div>
            <h2>
              Upload Documents
            </h2>

            <p>
              Drag and drop files here
              or browse from your computer.
            </p>

            <small>
              PDF, DOCX, TXT, CSV,
              XLSX, PPTX
            </small>
          </div>
        </div>

        <UploadBox
          onFilesSelected={
            handleFilesSelected
          }
          loading={loading}
          inputId="document-file-picker"
        />
      </section>

      { }

      <section className="documents-url-panel">
        <div className="documents-url-heading">
          <span className="documents-url-icon">
            <Globe2 size={17} />
          </span>

          <div>
            <h2>
              Add Website URL
            </h2>

            <p>
              Add a website as a
              research source.
            </p>
          </div>
        </div>

        <form
          onSubmit={handleAddUrl}
          className="documents-url-form"
        >
          <input
            id="url-input"
            type="url"
            value={url}
            onChange={(event) =>
              setUrl(
                event.target.value
              )
            }
            placeholder="https://example.com"
            aria-label="Research website URL"
          />

          <button
            type="submit"
            disabled={urlLoading}
            className="app-primary-button"
          >
            <Plus size={15} />

            {urlLoading
              ? "Adding..."
              : "Add URL"}
          </button>
        </form>
      </section>

      { }

      {error && (
        <div className="documents-feedback documents-feedback-error">
          {error}
        </div>
      )}

      { }

      {notice && (
        <div
          role="status"
          className="documents-feedback documents-feedback-success"
        >
          {notice}
        </div>
      )}

      { }

      <section className="documents-list-panel">
        <div className="documents-list-heading">
          <div>
            <h2>
              Your Documents
            </h2>

            <p>
              Manage your uploaded files
              and saved sources.
            </p>
          </div>

          <div className="documents-toolbar">
            <label className="documents-search">
              <Search size={16} />

              <input
                aria-label="Search documents"
                value={search}
                onChange={(event) =>
                  setSearch(
                    event.target.value
                  )
                }
                placeholder="Search documents..."
              />
            </label>

            <select
              className="documents-filter-select"
              aria-label="Filter document type"
              value={activeFilter}
              onChange={(event) =>
                setActiveFilter(
                  event.target.value
                )
              }
            >
              {filters.map(
                (filter) => (
                  <option
                    key={filter}
                    value={filter}
                  >
                    {filter === "All"
                      ? "All types"
                      : filter}
                  </option>
                )
              )}
            </select>
          </div>
        </div>

        {listLoading ||
        loading ||
        urlLoading ? (
          <div className="documents-empty-state">
            {listLoading
              ? "Loading sources..."
              : "Processing source..."}
          </div>
        ) : listError &&
          documents.length === 0 ? (
          <div className="documents-empty-state">
            <strong>
              {listError}
            </strong>

            <button
              type="button"
              className="app-primary-button"
              onClick={
                loadAllSources
              }
            >
              Retry
            </button>
          </div>
        ) : filteredDocuments.length ===
          0 ? (
          <div className="documents-empty-state">
            <FileText size={22} />

            <strong>
              {documents.length
                ? "No matching sources"
                : "No documents yet"}
            </strong>

            <span>
              {documents.length
                ? "Try another filter or search term."
                : "Upload your first document to start researching."}
            </span>
          </div>
        ) : (
          <div className="documents-table-wrap">
            { }

            <div className="documents-table-head">
              <span>Name</span>
              <span>Type</span>
              <span>Added</span>
              <span>Action</span>
            </div>

            { }

            <div className="documents-table-body">
              {filteredDocuments.map(
                (item, index) => {
                  const documentId =
                    item.id ||
                    item._id ||
                    `source-${index}`;

                  return (
                    <DocumentCard
                      key={`${item.source_type || "source"}-${documentId}`}
                      document={item}
                      onDelete={
                        handleDelete
                      }
                      deleting={
                        deletingId ===
                        documentId
                      }
                      compact
                      formatDate={
                        formatAddedDate
                      }
                      selected={
                        String(
                          documentId
                        ) ===
                        selectedId
                      }
                    />
                  );
                }
              )}
            </div>
          </div>
        )}

        <div className="documents-result-count">
          Showing{" "}
          {filteredDocuments.length}{" "}
          of {documents.length}{" "}
          sources
        </div>
      </section>
    </AppShell>
  );
}
