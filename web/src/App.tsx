import { useEffect, useRef, useState } from "react";
import { Answer, ApiError, Hit, Item, Me, Passage, Reopened, api, describe, loadToken, refHandle, saveToken } from "./api";

const ORIGIN: Record<string, string> = {
  human: "insan", assisted: "model, insan onaylı", model: "model", unknown: "köken bilinmiyor",
};

// kstd item information as one line: origin, license, validity, applicability, notices.
function ItemLine({ item }: { item?: Item }) {
  if (!item) return null;
  const valid = item.valid_from || item.valid_to ? ` · geçerli ${item.valid_from ?? "…"}–${item.valid_to ?? "…"}` : "";
  return (
    <span className="meta item-line">
      {ORIGIN[item.origin] ?? item.origin}
      {item.reviewed_by ? ` (${item.reviewed_by})` : ""} · lisans {item.license}
      {valid}
      {item.current ? "" : " · güncel değil"}
      {item.applies_to ? ` · ${item.applies_to}` : ""}
      {item.notices.length ? ` · ${item.notices.join("; ")}` : ""}
    </span>
  );
}

// Model output is shown as plain text: no Markdown, no HTML, no images (Astra review #3). Only [n] becomes a button.
function AnswerBody({ body, onCite }: { body: string; onCite: (n: number) => void }) {
  const parts = body.split(/\[(\d{1,3})\]/g);
  return (
    <p className="answer-body">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <button key={i} className="cite" onClick={() => onCite(Number(part))} title={`Kaynak ${part}`}>
            {part}
          </button>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  );
}

function PassagePanel({ passage, onClose }: { passage: Passage; onClose: () => void }) {
  const d = describe(passage.citation);
  return (
    <aside className="passage" aria-label="Kaynak pasaj">
      <header>
        <div>
          <div className="eyebrow">Kaynak</div>
          <div className="passage-title">{d.path}</div>
          <div className="meta">
            {d.book} · sürüm {d.version} · parça {d.ordinal}
            {passage.page ? ` · sayfa ${passage.page}` : ""}
          </div>
        </div>
        <button className="ghost" onClick={onClose} aria-label="Kapat">
          ×
        </button>
      </header>
      <pre className="passage-text">{passage.text ?? passage.withheld}</pre>
      <ItemLine item={passage.item} />
      <footer className="meta">Bu pasaj atıf yapılan sürümden, güncel yetkinizle açıldı.</footer>
    </aside>
  );
}

function Login({ onToken }: { onToken: (t: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <main className="login">
      <h1>Kütüphane</h1>
      <p>Kurum kimlik sağlayıcınızdan aldığınız erişim belirtecini yapıştırın.</p>
      <textarea id="token" value={value} onChange={(e) => setValue(e.target.value.trim())} rows={5} />
      <button className="primary" disabled={!value} onClick={() => onToken(value)}>
        Giriş yap
      </button>
    </main>
  );
}

// The workspace is keyed by the token: signing out or in as someone else unmounts it, so no answer, passage or
// result of a previous session survives, and replies to its pending requests have nowhere to land (Astra review #4).
export default function App() {
  const [token, setToken] = useState(loadToken());

  function signIn(t: string) {
    saveToken(t);
    setToken(t);
  }

  function signOut() {
    saveToken("");
    setToken("");
  }

  if (!token) return <Login onToken={signIn} />;
  return <Workspace key={token} token={token} onSignOut={signOut} />;
}

function Workspace({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [answer, setAnswer] = useState<Answer | Reopened | null>(null);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [answerId, setAnswerId] = useState("");
  // A reply that arrives after this session ended (signed out, or someone else signed in) must not act on the new one.
  const live = useRef(true);
  useEffect(() => {
    live.current = true; // StrictMode mounts twice in development
    return () => void (live.current = false);
  }, []);

  const fail = (e: unknown) => {
    if (!live.current) return;
    if (e instanceof ApiError && e.status === 401) onSignOut();
    setError(e instanceof Error ? e.message : "Beklenmeyen hata.");
  };

  useEffect(() => {
    api.whoami(token).then(setMe).catch(fail);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function run<T>(work: () => Promise<T>) {
    setBusy(true);
    setError("");
    try {
      return await work();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }

  const ask = () =>
    run(async () => {
      setHits(null);
      setPassage(null);
      setAnswer(await api.ask(token, question));
    });

  const search = () =>
    run(async () => {
      setAnswer(null);
      setPassage(null);
      setHits((await api.search(token, question)).results);
    });

  const reopen = () => run(async () => setAnswer(await api.reopen(token, answerId.trim())));
  const open = (handle: string) => run(async () => setPassage(await api.passage(token, handle)));

  const cite = (n: number) => {
    if (!answer) return;
    const ref = "evidence" in answer ? answer.evidence.find((e) => e.n === n)?.citation : undefined;
    const handle = ref ?? ("citations" in answer ? answer.citations.find((c) => c.n === n) : undefined);
    if (typeof handle === "string") open(handle);
    else if (handle) open(refHandle(handle));
  };

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">Kütüphane</span>
        <span className="meta">
          {me ? `${me.principal}${me.on_behalf_of ? ` · ${me.on_behalf_of} adına` : ""}` : "…"}
        </span>
        <button className="ghost" onClick={onSignOut}>
          Çıkış
        </button>
      </header>
      <div className={passage ? "work with-panel" : "work"}>
        <main>
          <section className="ask">
            <label htmlFor="question" className="eyebrow">
              Soru
            </label>
            <textarea
              id="question"
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Örn. Erişim kayıtları ne kadar süre saklanır?"
            />
            <div className="row">
              <button className="primary" disabled={busy || !question.trim()} onClick={ask}>
                Sor
              </button>
              <button disabled={busy || !question.trim()} onClick={search}>
                Yalnız ara
              </button>
            </div>
          </section>
          {error && <div className="error" role="alert">{error}</div>}
          {busy && <div className="meta">Çalışıyor…</div>}
          {answer && (
            <section className="result">
              {answer.status === "answered" && answer.body ? (
                <AnswerBody body={answer.body} onCite={cite} />
              ) : (
                <p className="empty">
                  Kütüphanede bu soruyu dayanaklı biçimde cevaplayan bir kaynak yok. Uydurma bir cevap üretilmedi.
                </p>
              )}
              {"withheld" in answer && answer.withheld ? (
                <div className="meta">
                  {answer.withheld} pasaj, kullanım hakları yapay zekâ girdisine izin vermediği için modele gönderilmedi.
                </div>
              ) : null}
              <div className="meta">Cevap kimliği: {answer.id}</div>
            </section>
          )}
          {hits && (
            <section className="result">
              {hits.length === 0 && <p className="empty">Okuma yetkiniz olan kitaplarda eşleşme yok.</p>}
              <ol className="hits">
                {hits.map((h) => {
                  const d = describe(h.citation);
                  return (
                    <li key={h.citation}>
                      <button className="hit" onClick={() => open(h.citation)}>
                        <span className="passage-title">{d.path}</span>
                        <span className="meta">
                          {d.book} · sürüm {d.version}
                        </span>
                        <span className="snippet">{(h.text ?? h.withheld ?? "").slice(0, 280)}</span>
                        <ItemLine item={h.item} />
                      </button>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}
          <section className="reopen">
            <label htmlFor="answer-id" className="eyebrow">
              Eski bir cevabı aç
            </label>
            <div className="row">
              <input id="answer-id" value={answerId} onChange={(e) => setAnswerId(e.target.value)} />
              <button disabled={busy || !answerId.trim()} onClick={reopen}>
                Aç
              </button>
            </div>
            <div className="meta">Model yeniden çağrılmaz; cevap ve kanıtı güncel yetkinizle gösterilir.</div>
          </section>
        </main>
        {passage && <PassagePanel passage={passage} onClose={() => setPassage(null)} />}
      </div>
    </div>
  );
}
