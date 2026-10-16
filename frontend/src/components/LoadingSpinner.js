export default function LoadingSpinner({
  text = "Loading...",
}) {
  return (
    <div className="flex items-center justify-center gap-3 py-6">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />

      <span className="text-sm text-slate-500">
        {text}
      </span>
    </div>
  );
}