export function plainText(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const document = new DOMParser().parseFromString(value, "text/html");
  return document.body.textContent?.replace(/\s+/g, " ").trim() || fallback;
}
