"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";

export default function UploadBox({
  onFilesSelected,
  loading = false,
  compact = false,
  featured = false,
  inputId,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] =
    useState(false);

  function handleFiles(files) {
    if (files?.length) {
      onFilesSelected?.(
        Array.from(files)
      );
    }
  }

  function handleDrop(event) {
    event.preventDefault();

    setDragging(false);

    handleFiles(
      event.dataTransfer.files
    );
  }

  function openFilePicker(event) {
    event?.stopPropagation();

    inputRef.current?.click();
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() =>
        setDragging(false)
      }
      onDrop={handleDrop}
      onClick={openFilePicker}
      className={[
        "upload-box",
        compact
          ? "upload-box-compact"
          : "",
        featured
          ? "upload-box-featured"
          : "",
        dragging
          ? "upload-box-dragging"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.csv,.xlsx,.pptx"
        className="hidden"
        onChange={(event) => {
          handleFiles(
            event.target.files
          );

          event.target.value = "";
        }}
      />

      <div className="upload-icon">
        <Upload size={22} />
      </div>

      <h3 className="upload-title">
        {loading
          ? "Processing documents..."
          : "Drag & drop files here"}
      </h3>

      <p className="upload-description">
        {loading
          ? "Please wait while your documents are processed."
          : "or browse from your computer"}
      </p>

      <p className="upload-formats">
        PDF · DOCX · TXT · CSV · XLSX · PPTX
      </p>

      <button
        type="button"
        className="app-primary-button upload-featured-button"
        disabled={loading}
        onClick={
          openFilePicker
        }
      >
        <Upload size={15} />

        {loading
          ? "Uploading..."
          : "Upload Documents"}
      </button>
    </div>
  );
}
