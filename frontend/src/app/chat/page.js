"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Square, X } from "lucide-react";

import { AppShell } from "../../components/Sidebar";
import ChatMessage from "../../components/ChatMessage";
import CitationCard from "../../components/CitationCard";
import LoadingSpinner from "../../components/LoadingSpinner";

import { apiRequest } from "../../lib/api";
import {
  filterRelevantCitations,
  getCitationIdentity,
} from "../../lib/citations";

const CHAT_STORAGE_KEY = "research_ai_conversation_id";
const ALLOWED_ATTACHMENT_EXTENSIONS = new Set([
  "pdf",
  "docx",
  "txt",
  "csv",
  "xlsx",
  "pptx",
]);

function AnswerAttribution({ message }) {
  const sources = filterRelevantCitations(
    Array.isArray(message.sources) && message.sources.length > 0
      ? message.sources
      : message.citations
  );

  return (
    <section aria-labelledby={`answer-sources-${message.id}`}>
      <h3
        id={`answer-sources-${message.id}`}
        className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500"
      >
        Sources ({sources.length})
      </h3>
      {sources.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {sources.map((citation, index) => (
            <CitationCard
              key={getCitationIdentity(citation)}
              citation={citation}
              sourceNumber={index + 1}
              summaryOnly
            />
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          No source metadata is available for this answer.
        </p>
      )}
    </section>
  );
}
const MAX_CHAT_ATTACHMENTS = 10;
const CHAT_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

export default function ChatPage({ embedded = false }) {
  const chatStorageKey = embedded
    ? `${CHAT_STORAGE_KEY}_embedded`
    : CHAT_STORAGE_KEY;
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [attachments, setAttachments] = useState([]);

  const [loading, setLoading] = useState(false);
  const [requestElapsedSeconds, setRequestElapsedSeconds] = useState(0);
  const [requestStage, setRequestStage] = useState("");
  const [conversationLoading, setConversationLoading] = useState(false);

  const [error, setError] = useState("");

  const messagesEndRef = useRef(null);
  const attachmentInputRef = useRef(null);
  const activeRequestRef = useRef(null);
  const requestSequenceRef = useRef(0);
  const loadingRef = useRef(false);
  const conversationLoadRef = useRef({
    sequence: 0,
    controller: null,
  });

  // -------------------------------------------------
  // Scroll to latest message
  // -------------------------------------------------

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  // -------------------------------------------------
  // Load conversation from backend
  // -------------------------------------------------

  const loadConversation = useCallback(async (conversationIdToLoad) => {
    const previousLoad = conversationLoadRef.current;
    previousLoad.controller?.abort();

    const sequence = previousLoad.sequence + 1;
    const controller = new AbortController();
    conversationLoadRef.current = { sequence, controller };

    try {
      setConversationLoading(true);
      setError("");

      const data = await apiRequest(
        `/history/conversations/${conversationIdToLoad}`,
        { signal: controller.signal }
      );
      if (conversationLoadRef.current.sequence !== sequence) {
        return;
      }

      setConversationId(conversationIdToLoad);
      sessionStorage.setItem(chatStorageKey, conversationIdToLoad);
      setMessages(data.messages || []);

      if (!embedded) {
        window.history.replaceState(
          null,
          "",
          `/chat?conversation_id=${conversationIdToLoad}`
        );
      }
    } catch (loadError) {
      if (
        controller.signal.aborted ||
        conversationLoadRef.current.sequence !== sequence
      ) {
        return;
      }

      console.error(loadError);
      sessionStorage.removeItem(chatStorageKey);
      setError(loadError.message || "Failed to load conversation.");
      setMessages([]);
      setConversationId(null);

      if (!embedded) {
        window.history.replaceState(null, "", "/chat");
      }
    } finally {
      if (conversationLoadRef.current.sequence === sequence) {
        conversationLoadRef.current = {
          sequence,
          controller: null,
        };
        setConversationLoading(false);
      }
    }
  }, [chatStorageKey, embedded]);

  // -------------------------------------------------
  // Load saved conversation
  // -------------------------------------------------

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    const conversationIdFromUrl =
      params.get("conversation_id");

    const savedConversationId =
      sessionStorage.getItem(chatStorageKey);

    const conversationToLoad =
      conversationIdFromUrl || savedConversationId;

    if (!conversationToLoad) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadConversation(conversationToLoad);
    }, 0);

    return () => {
      window.clearTimeout(timer);
      const activeLoad = conversationLoadRef.current;
      if (activeLoad.controller) {
        activeLoad.controller.abort();
        conversationLoadRef.current = {
          sequence: activeLoad.sequence + 1,
          controller: null,
        };
      }
    };
  }, [chatStorageKey, loadConversation]);

  useEffect(() => () => {
    activeRequestRef.current?.controller.abort();
    conversationLoadRef.current.controller?.abort();
  }, []);

  // -------------------------------------------------
  // Send question
  // -------------------------------------------------

  async function handleSubmit(event) {
    event.preventDefault();

    const cleanQuestion = question.trim();

    if (
      !cleanQuestion ||
      loadingRef.current ||
      conversationLoading
    ) {
      return;
    }

    setError("");

    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;
    const controller = new AbortController();
    const userMessageId = `user-${sequence}-${Date.now()}`;
    activeRequestRef.current = {
      sequence,
      controller,
      userMessageId,
    };
    loadingRef.current = true;

    const userMessage = {
      id: userMessageId,
      role: "user",
      content: cleanQuestion,
      citations: [],
      attachments: attachments.map((file) => ({
        filename: file.name,
        source_type: "file",
      })),
    };

    setMessages((current) => [
      ...current,
      userMessage,
    ]);

    setQuestion("");
    setLoading(true);
    setRequestElapsedSeconds(0);
    setRequestStage(
      attachments.length
        ? "Uploading and indexing attachments..."
        : "Researching your sources..."
    );

    let uploadedDocuments = [];
    let requestTimedOut = false;
    const requestStartedAt = Date.now();
    const elapsedIntervalId = window.setInterval(() => {
      setRequestElapsedSeconds(
        Math.floor((Date.now() - requestStartedAt) / 1000)
      );
    }, 1000);
    const timeoutId = window.setTimeout(() => {
      requestTimedOut = true;
      controller.abort();
    }, CHAT_REQUEST_TIMEOUT_MS);

    try {
      if (attachments.length) {
        const formData = new FormData();
        attachments.forEach((file) => {
          formData.append("files", file);
        });

        const uploadResponse = await apiRequest(
          "/documents/upload",
          {
            method: "POST",
            body: formData,
            signal: controller.signal,
          }
        );

        if (!Array.isArray(uploadResponse?.documents)) {
          throw new Error(
            "The server did not confirm that the attachments were processed."
          );
        }
        uploadedDocuments = uploadResponse.documents;

        if (uploadedDocuments.length !== attachments.length) {
          throw new Error(
            "The server did not confirm processing for every attachment."
          );
        }

        window.dispatchEvent(new Event("research:sources-updated"));
        setAttachments([]);
        if (attachmentInputRef.current) {
          attachmentInputRef.current.value = "";
        }
        setRequestStage("Researching your sources...");
      }

      const requestBody = {
        question: cleanQuestion,
        attachment_document_ids: uploadedDocuments
          .map((document) => document.id)
          .filter(Boolean),
      };

      // Continue existing conversation
      if (conversationId) {
        requestBody.conversation_id =
          conversationId;
      }

      const data = await apiRequest(
        "/chat/",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          signal: controller.signal,
          body: JSON.stringify(
            requestBody
          ),
        }
      );

      if (
        controller.signal.aborted ||
        requestSequenceRef.current !== sequence
      ) {
        return;
      }

      // Save conversation ID
      if (data.conversation_id) {
        setConversationId(
          data.conversation_id
        );

        sessionStorage.setItem(chatStorageKey, data.conversation_id);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("research:conversations-updated"));
        }

        // Update URL for persistence
        if (!embedded) {
          window.history.replaceState(
            null,
            "",
            `/chat?conversation_id=${data.conversation_id}`
          );
        }
      }

      const assistantMessage = {
        id: `assistant-${sequence}-${Date.now()}`,
        role: "assistant",

        content:
          data.answer ||
          "I could not generate an answer.",

        citations:
          data.citations || [],

        sources:
          data.sources || data.citations || [],

        searched_files:
          data.searched_files || [],

        source_attribution_version:
          data.source_attribution_version,
      };

      setMessages((current) => [
        ...current,
        assistantMessage,
      ]);
      setAttachments([]);
      if (attachmentInputRef.current) {
        attachmentInputRef.current.value = "";
      }
    } catch (requestError) {
      if (requestSequenceRef.current !== sequence) {
        return;
      }
      if (controller.signal.aborted && !requestTimedOut) {
        setMessages((current) =>
          current.filter((message) => message.id !== userMessageId)
        );
        return;
      }

      console.error(requestError);
      setMessages((current) =>
        current.filter((message) => message.id !== userMessageId)
      );

      setError(
        (requestTimedOut
          ? "Research took longer than five minutes, so this browser request was stopped. Check that the backend and Ollama model are responsive, then retry."
          : requestError.message) ||
          "Something went wrong while generating the answer."
      );
    } finally {
      window.clearTimeout(timeoutId);
      window.clearInterval(elapsedIntervalId);
      if (requestSequenceRef.current === sequence) {
        activeRequestRef.current = null;
        loadingRef.current = false;
        setLoading(false);
        setRequestStage("");
      }
    }
  }

  function handleStop() {
    const activeRequest = activeRequestRef.current;
    if (!activeRequest) {
      return;
    }

    requestSequenceRef.current += 1;
    activeRequestRef.current = null;
    loadingRef.current = false;
    activeRequest.controller.abort();
    setMessages((current) =>
      current.filter((message) => message.id !== activeRequest.userMessageId)
    );
    setLoading(false);
    setRequestStage("");
    setError(
      "Stopped waiting for this response. The backend may continue processing the request."
    );
  }

  function handleAttachmentsSelected(event) {
    const selectedFiles = Array.from(event.target.files || []);
    event.target.value = "";

    const nextAttachments = [...attachments];
    for (const file of selectedFiles) {
      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)) {
        setError(
          `Unsupported file type for "${file.name}". Choose PDF, DOCX, TXT, CSV, XLSX, or PPTX.`
        );
        continue;
      }
      if (
        nextAttachments.length >= MAX_CHAT_ATTACHMENTS
      ) {
        setError(
          `You can attach up to ${MAX_CHAT_ATTACHMENTS} files to one message.`
        );
        break;
      }
      nextAttachments.push(file);
    }

    setAttachments(nextAttachments);
  }

  function removeAttachment(attachmentIndex) {
    setAttachments((current) =>
      current.filter((_, index) => index !== attachmentIndex)
    );
  }

  // -------------------------------------------------
  // Start a completely new chat
  // -------------------------------------------------

  function handleNewChat() {
    requestSequenceRef.current += 1;
    activeRequestRef.current?.controller.abort();
    activeRequestRef.current = null;
    loadingRef.current = false;
    conversationLoadRef.current.controller?.abort();
    conversationLoadRef.current = {
      sequence: conversationLoadRef.current.sequence + 1,
      controller: null,
    };
    setLoading(false);
    setRequestStage("");
    setConversationLoading(false);

    // Clear messages
    setMessages([]);

    // Clear conversation ID
    setConversationId(null);

    // Remove saved conversation
    sessionStorage.removeItem(chatStorageKey);

    setQuestion("");
    setAttachments([]);
    setError("");
    if (attachmentInputRef.current) {
      attachmentInputRef.current.value = "";
    }

    // Remove conversation ID from URL
    if (!embedded) {
      window.history.replaceState(
        null,
        "",
        "/chat"
      );
    }
  }

  // -------------------------------------------------
  // UI
  // -------------------------------------------------

  return (
    <AppShell
      embedded={embedded}
      className={embedded ? "embedded-chat-page" : "chat-page"}
      contentClassName={embedded ? "embedded-chat-content" : "app-content chat-content"}
    >

            {/* Header */}
            <div className="app-page-header chat-page-header">

              <div>

                <p className="app-eyebrow">
                  Research Workspace
                </p>

                <h1 className="app-title">
                  Research Chat
                </h1>

                <p className="app-subtitle">
                  Ask questions about your uploaded documents
                  and website sources.
                </p>

              </div>

              {/* New Chat */}
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="app-secondary-button shrink-0"
                >
                  New Chat
                </button>
              )}

            </div>

            {/* Chat Area */}
            <div className="chat-frame">

              {/* Messages */}
              <div className="chat-messages flex-1 overflow-y-auto p-5 lg:p-8">

                {/* Loading old conversation */}
                {conversationLoading ? (

                  <div className="chat-empty-state">

                    <LoadingSpinner
                      text="Loading conversation..."
                    />

                  </div>

                ) : messages.length === 0 ? (

                  /* Empty Chat */
                  <div className="chat-empty-state">

                    <div className="max-w-2xl text-center">

                      <h2 className="text-xl font-semibold text-slate-900">
                        Ask your research question
                      </h2>

                      <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-500">
                        Ask questions about your uploaded PDFs,
                        DOCX files, TXT files, or added websites.
                      </p>

                      {/* Suggested Questions */}
                      <div className="mt-6 grid gap-3 text-left sm:grid-cols-2">

                        {/* Documents */}
                        <button
                          type="button"
                          onClick={() =>
                            setQuestion(
                              "What are the main concepts explained in my uploaded documents?"
                            )
                          }
                          className="chat-suggestion"
                        >
                          Ask about my documents
                        </button>

                        {/* Website */}
                        <button
                          type="button"
                          onClick={() =>
                            setQuestion(
                              "What does the LangChain website say about agents?"
                            )
                          }
                          className="chat-suggestion"
                        >
                          Ask about a website
                        </button>

                        {/* Comparison */}
                        <button
                          type="button"
                          onClick={() =>
                            setQuestion(
                              "Compare my LangChain PDF with the LangChain website."
                            )
                          }
                          className="chat-suggestion sm:col-span-2"
                        >
                          Compare a document and website
                        </button>

                      </div>

                    </div>

                  </div>

                ) : (

                  /* Messages */
                  <div className="space-y-5">

                    {messages.map((message) => (

                      <div key={message.id}>

                        <ChatMessage
                          role={message.role}
                          content={message.content}
                        />

                        {message.role === "user" &&
                          message.attachments?.length > 0 && (
                            <div className="mt-2 flex max-w-3xl flex-wrap gap-2">
                              {message.attachments.map((attachment, index) => (
                                <span
                                  key={`${attachment.document_id || attachment.filename || "attachment"}-${index}`}
                                  className="chat-attachment-chip"
                                >
                                  <Paperclip size={13} />
                                  {attachment.filename || "Attachment"}
                                </span>
                              ))}
                            </div>
                          )}

                        {/* Retrieval and answer evidence */}
                        {message.role !== "user" && (
                          <div className="ml-0 mt-3 max-w-3xl">
                            <AnswerAttribution message={message} />
                          </div>
                        )}

                      </div>

                    ))}

                    {/* Loading */}
                    {loading && (

                      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">

                        <LoadingSpinner
                          text={`${requestStage || "Researching your sources..."} ${requestElapsedSeconds}s elapsed`}
                        />

                      </div>

                    )}

                    <div ref={messagesEndRef} />

                  </div>

                )}

              </div>

              {/* Error */}
              {error && (

                <div className="chat-error">
                  {error}
                </div>

              )}

              {/* Question Input */}
              <div className="chat-composer">

                <form
                  onSubmit={handleSubmit}
                  className="flex flex-col gap-3"
                >
                  {attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {attachments.map((attachment, index) => (
                        <span
                          key={`${attachment.name}-${attachment.size}-${attachment.lastModified}-${index}`}
                          className="chat-attachment-chip"
                        >
                          <Paperclip size={13} />
                          <span className="max-w-56 truncate">
                            {attachment.name}
                          </span>
                          <button
                            type="button"
                            onClick={() => removeAttachment(index)}
                            disabled={loading}
                            aria-label={`Remove ${attachment.name}`}
                            className="chat-attachment-remove"
                          >
                            <X size={13} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                    <input
                      ref={attachmentInputRef}
                      type="file"
                      multiple
                      accept=".pdf,.docx,.txt,.csv,.xlsx,.pptx"
                      className="hidden"
                      onChange={handleAttachmentsSelected}
                    />

                    <button
                      type="button"
                      className="app-secondary-button chat-attach"
                      disabled={loading || conversationLoading}
                      onClick={() => attachmentInputRef.current?.click()}
                    >
                      <Paperclip size={15} />
                      Attach
                    </button>

                    <div className="min-w-0 flex-1">
                      <textarea
                        value={question}
                        onChange={(event) =>
                          setQuestion(event.target.value)
                        }
                        onKeyDown={(event) => {
                          if (
                            event.key === "Enter" &&
                            !event.shiftKey &&
                            !event.nativeEvent.isComposing
                          ) {
                            event.preventDefault();
                            handleSubmit(event);
                          }
                        }}
                        rows={2}
                        placeholder="Ask your research question..."
                        className="app-input chat-textarea"
                        disabled={conversationLoading}
                      />

                      <p className="chat-hint">
                        Press Enter to send • Shift + Enter for a new line
                      </p>
                    </div>

                    {loading ? (
                      <button
                        type="button"
                        onClick={handleStop}
                        className="app-secondary-button chat-submit chat-stop"
                      >
                        <Square size={13} fill="currentColor" />
                        Stop
                      </button>
                    ) : (
                      <button
                        type="submit"
                        disabled={
                          conversationLoading ||
                          !question.trim()
                        }
                        className="app-primary-button chat-submit"
                      >
                        Ask AI
                      </button>
                    )}

                  </div>
                </form>

              </div>

            </div>

    </AppShell>
  );
}
