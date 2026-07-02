/**
 * Socrata date parsing.
 *
 * GOTCHA (verified live 2026-07-02): datos.gov.co fuel datasets store dates
 * NON-zero-padded — e.g. "2025-9-01", month field "2". Lexical sorting is
 * therefore WRONG ("2025-9-01" > "2025-12-01" as strings). Always parse to a
 * real Date before comparing. This function is the single choke point that
 * encodes the gotcha so no caller re-learns it.
 */
export function parseSocrataDate(raw: string): Date {
  const [y, m = "1", d = "1"] = raw.trim().split(/[-/T ]/);
  const year = Number(y);
  const month = Number(m);
  const day = Number(d);
  // UTC to avoid TZ drift on date-only values.
  return new Date(Date.UTC(year, month - 1, day));
}

/** ISO YYYY-MM-DD from a Socrata date string. */
export function toIsoDate(raw: string): string {
  return parseSocrataDate(raw).toISOString().slice(0, 10);
}
