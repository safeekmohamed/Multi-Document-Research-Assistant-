export function parseCsv(text, maxRows = 301) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  let index = 0;
  for (; index < text.length && rows.length < maxRows; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') { cell += '"'; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { row.push(cell); cell = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += char;
  }
  if (rows.length < maxRows && (cell || row.length)) { row.push(cell); rows.push(row); }
  if (rows[0]?.[0]?.startsWith("\uFEFF")) rows[0][0] = rows[0][0].slice(1);
  return { rows: rows.filter((item) => item.some((value) => value.length)), truncated: index < text.length };
}
