"use client";

import { openDocument } from "../lib/api";

import {
  FileText,
  Globe2,
  FileSpreadsheet,
  File,
} from "lucide-react";

export default function DocumentCard({
  document,
  onDelete,
  deleting = false,
  showActions = true,
  showManage = false,
  onManage,
  compact = false,
  formatDate,
  selected = false,
}) {
  const fileType =
    document?.file_type?.toLowerCase() ||
    "file";

  const isUrl =
    String(
      document?.source_type || ""
    ).toLowerCase() === "url";

  const documentId =
    document?.id || document?._id;

const addedDate =
    document?.created_at ||
    document?.uploaded_at ||
    document?.upload_date ||
    document?.createdAt ||
    document?.uploadedAt ||
    document?.date ||
    null;

function handleView() {
    if (
      isUrl &&
      document?.source_url
    ) {
      window.open(
        document.source_url,
        "_blank",
        "noopener,noreferrer"
      );

      return;
    }

    if (!documentId) {
      return;
    }

    openDocument(documentId);
  }

function getViewButtonText() {
    return isUrl
      ? "Open"
      : "View";
  }

if (compact) {
    const SourceIcon = isUrl
      ? Globe2
      : ["xlsx", "csv"].includes(
          fileType
        )
      ? FileSpreadsheet
      : fileType === "pdf"
      ? FileText
      : File;

    const sourceName =
      document?.filename ||
      document?.title ||
      document?.source_url ||
      "Untitled source";

    return (
      <div
        id={
          documentId
            ? `source-${documentId}`
            : undefined
        }
        className={`documents-table-row${
          selected
            ? " is-selected"
            : ""
        }`}
      >
        { }

        <div className="documents-row-source">
          <span
            className={`documents-row-icon ${
              isUrl
                ? "web"
                : fileType === "pdf"
                ? "pdf"
                : "file"
            }`}
          >
            <SourceIcon size={17} />
          </span>

          <div>
            <strong
              title={sourceName}
            >
              {sourceName}
            </strong>

            <small>
              {isUrl
                ? document?.source_url
                : "Uploaded document"}
            </small>
          </div>
        </div>

        { }

        <span className="documents-row-type">
          {isUrl
            ? "Website"
            : fileType.toUpperCase()}
        </span>

        { }

        <span className="documents-row-date">
          {formatDate &&
          addedDate
            ? formatDate(
                addedDate
              )
            : "—"}
        </span>

        { }

        <div className="documents-row-actions">
          {showActions && (
            <>
              <button
                type="button"
                onClick={
                  handleView
                }
                className="documents-view-button"
              >
                {getViewButtonText()}
              </button>

              <button
                type="button"
                onClick={() =>
                  onDelete?.(
                    document
                  )
                }
                disabled={
                  deleting
                }
                className="documents-remove-button"
              >
                {deleting
                  ? "Removing..."
                  : "Delete"}
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

return (
    <div className="document-card">
      <div className="document-card-icon">
        {isUrl
          ? "WEB"
          : fileType.toUpperCase()}
      </div>

      <div className="document-card-details">
        <h3 className="document-card-title">
          {document?.filename ||
            "Untitled document"}
        </h3>

        <p className="document-card-description">
          {isUrl
            ? "Website source"
            : "Uploaded document"}
        </p>

        {document?.source_url && (
          <p className="document-card-url">
            {document.source_url}
          </p>
        )}
      </div>

      <span className="document-card-type">
        {document?.source_type ||
          "file"}
      </span>

      <div className="document-card-actions">
        {showManage && (
          <button
            type="button"
            onClick={onManage}
            className="app-primary-button document-card-action"
          >
            Manage
          </button>
        )}

        {showActions && (
          <>
            <button
              type="button"
              onClick={
                handleView
              }
              className="app-secondary-button document-card-action"
            >
              {getViewButtonText()}
            </button>

            {onDelete && (
              <button
                type="button"
                onClick={() =>
                  onDelete(
                    document
                  )
                }
                disabled={
                  deleting
                }
                className="document-delete-button"
              >
                {deleting
                  ? "Deleting..."
                  : "Delete"}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}