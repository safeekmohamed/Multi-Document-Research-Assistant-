"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "../../components/Sidebar";
import LoadingSpinner from "../../components/LoadingSpinner";
import CitationCard from "../../components/CitationCard";

import { apiRequest } from "../../lib/api";
import {
  deduplicateCitations,
  getCitationIdentity,
} from "../../lib/citations";

import {
  MessageSquare,
  Search,
  ArrowRight,
  User,
  Bot,
  CalendarDays,
} from "lucide-react";

export default function HistoryPage() {
  const [conversations, setConversations] =
    useState([]);

  const [selectedConversation, setSelectedConversation] =
    useState(null);

  const [messages, setMessages] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [messageLoading, setMessageLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const [search, setSearch] =
    useState("");

useEffect(() => {
    loadConversations();
  }, []);

  async function loadConversations() {
    try {
      setLoading(true);
      setError("");

      const data = await apiRequest(
        "/history/conversations"
      );

      setConversations(
        data.conversations || []
      );
    } catch (error) {
      console.error(error);

      setError(
        error.message ||
          "Failed to load conversation history."
      );
    } finally {
      setLoading(false);
    }
  }

async function openConversation(
    conversation
  ) {
    try {
      setSelectedConversation(
        conversation
      );

      setMessages([]);

      setMessageLoading(true);

      setError("");

      const data = await apiRequest(
        `/history/conversations/${conversation.id}`
      );

      setMessages(
        data.messages || []
      );
    } catch (error) {
      console.error(error);

      setError(
        error.message ||
          "Failed to load conversation."
      );

      setMessages([]);
    } finally {
      setMessageLoading(false);
    }
  }

function continueConversation() {
    if (
      !selectedConversation?.id
    ) {
      return;
    }

    window.location.href =
      `/chat?conversation_id=${selectedConversation.id}`;
  }

function formatDate(value) {
    if (!value) {
      return "";
    }

    const date = new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return "";
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

  function formatDateTime(value) {
    if (!value) {
      return "";
    }

    const date = new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return "";
    }

    return date.toLocaleString(
      undefined,
      {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }
    );
  }

const filteredConversations =
    useMemo(() => {
      const query =
        search
          .trim()
          .toLowerCase();

      if (!query) {
        return conversations;
      }

      return conversations.filter(
        (conversation) => {
          const title =
            String(
              conversation?.title ||
                ""
            ).toLowerCase();

          return title.includes(
            query
          );
        }
      );
    }, [
      conversations,
      search,
    ]);

return (
    <AppShell
      className="history-page"
      contentClassName="app-content history-content"
    >
      {

}

      <div className="app-page-header history-page-heading">
        <div>
          <p className="app-eyebrow">
            Research Workspace
          </p>

          <h1 className="app-title">
            Research History
          </h1>

          <p className="app-subtitle">
            Review and continue your
            previous research conversations.
          </p>
        </div>
      </div>

      {

}

      {error && (
        <div className="history-error">
          {error}
        </div>
      )}

      {

}

      {loading ? (
        <LoadingSpinner
          text="Loading conversations..."
        />
      ) : (
        <div className="history-layout">
          {

}

          <section className="history-selector-panel">
            { }

            <div className="history-list-header">
              <div>
                <p className="app-eyebrow">
                  Research History
                </p>

                <h2 className="section-title">
                  Conversations
                </h2>
              </div>

              <span className="count-badge">
                {conversations.length}
              </span>
            </div>

            { }

            {conversations.length > 0 && (
              <div className="history-search">
                <Search size={16} />

                <input
                  type="text"
                  value={search}
                  onChange={(event) =>
                    setSearch(
                      event.target.value
                    )
                  }
                  placeholder="Search conversations..."
                />
              </div>
            )}

            { }

            {conversations.length ===
            0 ? (
              <div className="history-empty">
                <MessageSquare
                  size={24}
                />

                <strong>
                  No conversations yet
                </strong>

                <p>
                  Your previous research
                  conversations will appear
                  here.
                </p>
              </div>
            ) : filteredConversations.length ===
              0 ? (
              <div className="history-empty">
                <Search size={22} />

                <strong>
                  No conversations found
                </strong>

                <p>
                  Try a different search.
                </p>
              </div>
            ) : (
              <div className="history-conversation-list">
                {filteredConversations.map(
                  (conversation) => {
                    const isSelected =
                      String(
                        selectedConversation?.id
                      ) ===
                      String(
                        conversation.id
                      );

                    return (
                      <button
                        type="button"
                        key={
                          conversation.id
                        }
                        onClick={() =>
                          openConversation(
                            conversation
                          )
                        }
                        className={`history-conversation-card ${
                          isSelected
                            ? "is-selected"
                            : ""
                        }`}
                      >
                        { }

                        <div className="history-conversation-icon">
                          <MessageSquare
                            size={17}
                          />
                        </div>

                        { }

                        <div className="history-conversation-info">
                          <strong
                            title={
                              conversation.title ||
                              "New Conversation"
                            }
                          >
                            {conversation.title ||
                              "New Conversation"}
                          </strong>

                          <div className="history-conversation-meta">
                            <CalendarDays
                              size={12}
                            />

                            <span>
                              {formatDate(
                                conversation.created_at
                              ) ||
                                "No date"}
                            </span>
                          </div>
                        </div>

                        { }

                        <ArrowRight
                          size={16}
                          className="history-conversation-arrow"
                        />
                      </button>
                    );
                  }
                )}
              </div>
            )}
          </section>

          {

}

          <section className="history-messages-panel">
            { }

            {!selectedConversation ? (
              <div className="history-empty-state">
                <div className="history-empty-state-icon">
                  <MessageSquare
                    size={24}
                  />
                </div>

                <h2>
                  Select a conversation
                </h2>

                <p>
                  Choose a conversation
                  from the left to view
                  your complete research
                  messages.
                </p>
              </div>
            ) : messageLoading ? (
              <LoadingSpinner
                text="Loading conversation..."
              />
            ) : (
              <div className="history-message-content">
                {

}

                <div className="history-conversation-header">
                  <div>
                    <p className="app-eyebrow">
                      Research Conversation
                    </p>

                    <h2>
                      {selectedConversation.title ||
                        "New Conversation"}
                    </h2>

                    {selectedConversation.created_at && (
                      <div className="history-header-date">
                        <CalendarDays
                          size={14}
                        />

                        <span>
                          {formatDateTime(
                            selectedConversation.created_at
                          )}
                        </span>
                      </div>
                    )}
                  </div>

                  <span className="history-message-count">
                    {messages.length}{" "}
                    {messages.length ===
                    1
                      ? "message"
                      : "messages"}
                  </span>
                </div>

                {

}

                <div className="history-message-list">
                  {messages.length ===
                  0 ? (
                    <div className="history-no-messages">
                      <MessageSquare
                        size={22}
                      />

                      <p>
                        No messages found
                        in this conversation.
                      </p>
                    </div>
                  ) : (
                    messages.map(
                      (message, index) => {
                        const isUser =
                          message.role ===
                          "user";
                        const sources = deduplicateCitations(
                          Array.isArray(message.sources) && message.sources.length > 0
                            ? message.sources
                            : message.citations
                        );

                        return (
                          <div
                            key={
                              message.id ||
                              `message-${index}`
                            }
                            className={`history-message-wrapper ${
                              isUser
                                ? "user-message"
                                : "ai-message"
                            }`}
                          >
                            { }

                            <div
                              className={`history-message-avatar ${
                                isUser
                                  ? "user-avatar"
                                  : "ai-avatar"
                              }`}
                            >
                              {isUser ? (
                                <User
                                  size={15}
                                />
                              ) : (
                                <Bot
                                  size={16}
                                />
                              )}
                            </div>

                            { }

                            <div
                              className={`history-message ${
                                isUser
                                  ? "history-user-message"
                                  : "history-ai-message"
                              }`}
                            >
                              <div className="history-message-role">
                                {isUser
                                  ? "You"
                                  : "Research AI"}
                              </div>

                              <div className="history-message-text">
                                {
                                  message.content
                                }
                              </div>

                              { }

                              {!isUser && (
                                <div className="history-citations">
                                  <p className="history-citations-title">
                                    Sources ({sources.length})
                                  </p>

                                  {sources.length > 0 ? (
                                    <div className="grid gap-2 sm:grid-cols-2">
                                      {sources.map((citation, citationIndex) => (
                                        <CitationCard
                                          key={getCitationIdentity(citation)}
                                          citation={citation}
                                          sourceNumber={citationIndex + 1}
                                        />
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="conversation-empty">
                                      No source metadata is available for this answer.
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      }
                    )
                  )}
                </div>

                {

}

                {messages.length >
                  0 && (
                  <div className="history-continue">
                    <button
                      type="button"
                      onClick={
                        continueConversation
                      }
                      className="app-primary-button"
                    >
                      Continue Research
                      <ArrowRight
                        size={16}
                      />
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
