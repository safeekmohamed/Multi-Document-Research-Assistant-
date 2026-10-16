export default function ChatMessage({
  role,
  content,
}) {
  const isUser = role === "user";

  return (
    <div
      className={`flex ${
        isUser
          ? "justify-end"
          : "justify-start"
      }`}
    >
      <div
        className={`max-w-3xl rounded-lg px-4 py-3 ${
          isUser
            ? "bg-indigo-600 text-white"
            : "border border-slate-200 bg-slate-50 text-slate-700"
        }`}
      >

        <p
          className={`mb-2 text-xs font-semibold ${
            isUser
              ? "text-indigo-100"
              : "text-indigo-600"
          }`}
        >
          {isUser ? "You" : "Research AI"}
        </p>

        <p className="whitespace-pre-wrap text-sm leading-6">
          {content}
        </p>

      </div>
    </div>
  );
}
