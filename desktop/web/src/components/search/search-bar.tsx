"use client";

import { useState } from "react";

export function SearchBar({
  onSubmit,
  initial = "",
}: {
  onSubmit: (q: string) => void;
  initial?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSubmit(value.trim());
      }}
      className="flex gap-2"
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Describe what you're looking for…"
        className="flex-1 rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={!value.trim()}
        className="px-4 py-2 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        Search
      </button>
    </form>
  );
}
