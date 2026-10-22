// Same-origin calls to Kütüphane Core. The token lives in memory (and sessionStorage for this tab only).

// kstd item information of a file (docs/11 §8); null when its book has no kstd.yaml.
export type Item = {
  issuer: string;
  origin: "human" | "assisted" | "model" | "unknown";
  reviewed_by: string | null; // set only for origin "assisted"
  license: string;
  holder: string | null;
  valid_from: string | null;
  valid_to: string | null;
  applies_to: string | null;
  notices: string[];
  current: boolean;
} | null;
// text is null (with `withheld`) when the reader is a model and the item does not allow AI input.
export type Hit = { citation: string; page: number | null; line?: number | null; score: number; text: string | null; withheld?: string; item?: Item };
export type Ref = { n: number; book: string; content_id: string; profile_id: string; path: string; ordinal: number; item?: Item };
export type Answer = {
  id: string;
  status: "answered" | "not_in_library";
  body: string | null;
  citations: Ref[];
  correlation_id?: string;
  withheld?: number;
};
export type Reopened = {
  id: string;
  question: string;
  status: Answer["status"];
  body: string | null;
  evidence: { n: number; citation: string; text: string | null; withheld?: string; item?: Item }[];
};
export type Passage = { citation: string; page: number | null; line?: number | null; text: string | null; withheld?: string; item?: Item };
export type Me = { principal: string; on_behalf_of: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const KEY = "kutuphane.token";

export function loadToken(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the token stays in memory only */
  }
}

const MESSAGES: Record<number, string> = {
  400: "İstek geçersiz.",
  401: "Oturum geçersiz ya da süresi doldu. Yeniden giriş yapın.",
  403: "Bu içerik için şu anda yetkiniz yok.",
  404: "Bulunamadı.",
  409: "Yetkiler istek sırasında değişti; tekrar deneyin.",
  502: "Model hizmetine ulaşılamadı.",
};

async function call<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).error ?? "";
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, MESSAGES[res.status] ?? `Beklenmeyen hata (${res.status}). ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  whoami: (t: string) => call<Me>(t, "/v1/whoami"),
  search: (t: string, q: string) => call<{ results: Hit[] }>(t, `/v1/search?q=${encodeURIComponent(q)}&k=10`),
  ask: (t: string, question: string) => call<Answer>(t, "/v1/ask", { method: "POST", body: JSON.stringify({ question }) }),
  reopen: (t: string, id: string) => call<Reopened>(t, `/v1/answers/${encodeURIComponent(id)}`),
  passage: (t: string, handle: string) => call<Passage>(t, `/v1/citation?handle=${encodeURIComponent(handle)}`),
};

export function refHandle(r: Ref): string {
  return `${r.book}@${r.content_id}/${r.profile_id}/${r.path}#${r.ordinal}`;
}

// "book@ct_…/pf_…/path#n" → parts for display (short version ids).
export function describe(handle: string): { book: string; version: string; path: string; ordinal: string } {
  const [head, ordinal = ""] = [handle.slice(0, handle.lastIndexOf("#")), handle.slice(handle.lastIndexOf("#") + 1)];
  const at = head.indexOf("@");
  const book = head.slice(0, at);
  const [content, , ...rest] = head.slice(at + 1).split("/");
  return { book, version: content.slice(3, 11), path: rest.join("/"), ordinal };
}
