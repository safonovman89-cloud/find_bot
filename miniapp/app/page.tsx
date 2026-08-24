"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type SourceKey = "rsed" | "esku" | "kb" | "files";
type View = "search" | "history" | "help";

type DocumentItem = {
  source: SourceKey;
  title: string;
  url: string;
  bloom: string;
};

type SearchDocument = DocumentItem & {
  normalizedTitle: string;
  normalizedText: string;
  bloomBytes: Uint8Array;
};

type SearchResult = DocumentItem & {
  score: number;
  snippet: string;
  matchedTerms: number;
};

type HistoryItem = {
  query: string;
  systemKey: string | null;
  createdAt: string;
};

type SystemDefinition = {
  key: string;
  label: string;
  aliases: string[];
  source?: SourceKey;
};

type MaxWebApp = {
  ready?: () => void;
  openLink?: (url: string) => void;
  initDataUnsafe?: { user?: { first_name?: string } };
};

const SYSTEMS: SystemDefinition[] = [
  { key: "rsed", label: "РСЭД", aliases: ["рсэд", "directum", "диадок"], source: "rsed" },
  { key: "esku", label: "ГИС ЕСКУ", aliases: ["гис еску", "еску"], source: "esku" },
  { key: "r7", label: "Р7-Офис", aliases: ["р7-офис", "р7 офис", "р7", "office.yanao.ru"] },
  { key: "rsud", label: "РСУД", aliases: ["рсуд"] },
  { key: "epd", label: "ЕПД", aliases: ["епд"] },
  { key: "esv", label: "ЕСВ", aliases: ["есв"] },
  { key: "sreda", label: "Среда", aliases: ["среда"] },
  { key: "bbb", label: "Видеоконференции", aliases: ["bigbluebutton", "bbb", "видеоконференц"] },
  { key: "vipnet", label: "ViPNet", aliases: ["vipnet", "випнет"] },
];

const SOURCE_LABELS: Record<SourceKey, string> = {
  rsed: "Инструкции РСЭД",
  esku: "ГИС ЕСКУ",
  kb: "База знаний ЯНАО",
  files: "Документы ЯНАО",
};

const STOP_WORDS = new Set([
  "как", "где", "что", "это", "для", "или", "при", "про", "мне", "моя", "мой",
  "нужно", "можно", "надо", "если", "его", "ее", "ещё", "еще", "почему", "когда",
  "через", "после", "перед", "быть", "есть", "система", "системе", "системы",
]);

const HISTORY_KEY = "yanao-miniapp-history-v1";
const CONTEXT_KEY = "yanao-miniapp-context-v1";

function Icon({ name }: { name: "search" | "history" | "help" | "arrow" | "external" | "close" | "book" }) {
  const paths = {
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
    history: <><path d="M3.8 12a8.2 8.2 0 1 0 2.4-5.8L4 8.4" /><path d="M4 4.5v4h4" /><path d="M12 7.5V12l3 1.8" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.8 9a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.2.9-1.2 1.8" /><path d="M12 17h.01" /></>,
    arrow: <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>,
    external: <><path d="M14 5h5v5" /><path d="m19 5-8 8" /><path d="M17 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5" /></>,
    close: <><path d="m7 7 10 10" /><path d="m17 7-10 10" /></>,
    book: <><path d="M5 4.5h10a2 2 0 0 1 2 2V20H7a2 2 0 0 1-2-2z" /><path d="M7 17h10" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function normalize(value: string) {
  return value.toLocaleLowerCase("ru-RU").replaceAll("ё", "е").replace(/\s+/g, " ").trim();
}

function stem(word: string) {
  if (word.length < 5) return word;
  return word.replace(/(иями|ями|ами|ого|ему|ому|ыми|ими|иях|ах|ях|ия|ие|ий|ый|ая|ое|ую|ей|ов|ам|ям|ом|ем|ить|ать|ять|ться|ть|ы|и|а|я|е|у|ю)$/u, "");
}

function queryTerms(query: string) {
  const words = normalize(query).match(/[a-zа-я0-9]{2,}/giu) ?? [];
  return [...new Set(words.filter((word) => !STOP_WORDS.has(word)).map(stem).filter((word) => word.length >= 2))];
}

function detectSystem(query: string) {
  const value = normalize(query);
  return SYSTEMS.find((system) => system.aliases.some((alias) => value.includes(normalize(alias)))) ?? null;
}

function matchesSystem(document: SearchDocument, system: SystemDefinition) {
  if (system.source && document.source === system.source) return true;
  return system.aliases.some((alias) => {
    const aliasTerms = queryTerms(alias);
    return document.normalizedText.includes(normalize(alias)) || aliasTerms.every((term) => bloomHas(document.bloomBytes, term));
  });
}

function countMatches(text: string, term: string) {
  let count = 0;
  let position = 0;
  while (count < 8) {
    position = text.indexOf(term, position);
    if (position < 0) break;
    count += 1;
    position += term.length;
  }
  return count;
}

function fnv1a(value: string, seed: number) {
  let result = seed >>> 0;
  for (const byte of new TextEncoder().encode(value)) {
    result ^= byte;
    result = Math.imul(result, 16777619) >>> 0;
  }
  return result;
}

function decodeBloom(value: string) {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function bloomHas(signature: Uint8Array, term: string) {
  const seeds = [2166136261, 519786371, 3144134277];
  return seeds.every((seed) => {
    const position = fnv1a(term, seed) % (signature.length * 8);
    return (signature[Math.floor(position / 8)] & (1 << (position % 8))) !== 0;
  });
}

function makeSummary(result: SearchResult | undefined, termCount: number) {
  if (!result) return "Подходящих материалов не найдено. Попробуйте уточнить название системы и действие.";
  const matchText = termCount > 0 ? `Совпало ключевых слов: ${result.matchedTerms} из ${termCount}.` : "Материал относится к выбранной системе.";
  return `Наиболее подходящий материал — «${result.title}». ${matchText} Откройте карточку ниже, чтобы посмотреть полную инструкцию.`;
}

function readHistory(): HistoryItem[] {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(value) ? value.slice(0, 12) : [];
  } catch {
    return [];
  }
}

export default function Home() {
  const [documents, setDocuments] = useState<SearchDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [contextKey, setContextKey] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [view, setView] = useState<View>("search");
  const [firstName, setFirstName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const activeSystem = useMemo(() => SYSTEMS.find((system) => system.key === contextKey) ?? null, [contextKey]);

  useEffect(() => {
    const max = (window as typeof window & { WebApp?: MaxWebApp }).WebApp;
    max?.ready?.();
    queueMicrotask(() => {
      setFirstName(max?.initDataUnsafe?.user?.first_name ?? "");
      setHistory(readHistory());
      setContextKey(localStorage.getItem(CONTEXT_KEY));
    });
    fetch(new URL("search-index.json", document.baseURI))
      .then((response) => {
        if (!response.ok) throw new Error("Index unavailable");
        return response.json() as Promise<{ documents: DocumentItem[] }>;
      })
      .then((payload) => {
        setDocuments(payload.documents.map((document) => ({
          ...document,
          normalizedTitle: normalize(document.title),
          normalizedText: normalize(`${document.title} ${document.url}`),
          bloomBytes: decodeBloom(document.bloom),
        })));
        setLoading(false);
      })
      .catch(() => {
        setLoadError(true);
        setLoading(false);
      });
  }, []);

  function performSearch(value: string, forcedSystem?: SystemDefinition | null) {
    const cleanQuery = value.trim();
    if (!cleanQuery || loading) return;
    const explicitSystem = detectSystem(cleanQuery);
    const system = forcedSystem === undefined ? explicitSystem || activeSystem : forcedSystem;
    if (explicitSystem) {
      setContextKey(explicitSystem.key);
      localStorage.setItem(CONTEXT_KEY, explicitSystem.key);
    }
    const terms = queryTerms(cleanQuery).filter((term) => !system?.aliases.some((alias) => stem(normalize(alias)) === term));
    const normalizedQuery = normalize(cleanQuery);
    const ranked = documents
      .filter((document) => !system || matchesSystem(document, system))
      .map((document) => {
        let score = 0;
        let matchedTerms = 0;
        for (const term of terms) {
          const titleMatches = countMatches(document.normalizedTitle, term);
          const textMatches = bloomHas(document.bloomBytes, term) ? 1 : 0;
          if (textMatches > 0) matchedTerms += 1;
          score += titleMatches * 14 + Math.min(textMatches, 5) * 2;
        }
        if (normalizedQuery.length > 5 && document.normalizedText.includes(normalizedQuery)) score += 24;
        if (terms.length > 1 && matchedTerms === terms.length) score += 18;
        if (system?.source === document.source) score += 7;
        if (system && system.aliases.some((alias) => document.normalizedTitle.includes(normalize(alias)))) score += 8;
        return { ...document, score, matchedTerms };
      })
      .filter((document) => document.score > 0 && (terms.length === 0 || document.matchedTerms > 0))
      .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title, "ru"))
      .slice(0, 6)
      .map((document) => ({
        ...document,
        snippet: `${SOURCE_LABELS[document.source]}. Совпало ключевых слов: ${document.matchedTerms}${terms.length ? ` из ${terms.length}` : ""}.`,
      }));
    setSubmittedQuery(cleanQuery);
    setResults(ranked);
    setView("search");
    const item: HistoryItem = { query: cleanQuery, systemKey: system?.key ?? null, createdAt: new Date().toISOString() };
    const next = [item, ...history.filter((entry) => normalize(entry.query) !== normalize(cleanQuery))].slice(0, 12);
    setHistory(next);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    performSearch(query);
  }

  function chooseSystem(system: SystemDefinition) {
    setQuery(`${system.label} `);
    setContextKey(system.key);
    localStorage.setItem(CONTEXT_KEY, system.key);
    setSubmittedQuery("");
    setResults([]);
    setView("search");
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function clearContext() {
    setContextKey(null);
    localStorage.removeItem(CONTEXT_KEY);
    setSubmittedQuery("");
    setResults([]);
  }

  function repeatHistory(item: HistoryItem) {
    const system = SYSTEMS.find((candidate) => candidate.key === item.systemKey) ?? null;
    setQuery(item.query);
    setContextKey(system?.key ?? null);
    if (system) localStorage.setItem(CONTEXT_KEY, system.key);
    else localStorage.removeItem(CONTEXT_KEY);
    performSearch(item.query, system);
  }

  function openResult(url: string) {
    const max = (window as typeof window & { WebApp?: MaxWebApp }).WebApp;
    if (max?.openLink) max.openLink(url);
    else window.open(url, "_blank", "noopener,noreferrer");
  }

  const terms = queryTerms(submittedQuery);
  const summary = makeSummary(results[0], terms.length);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">Я</div>
        <div className="brand-copy"><strong>База знаний ЯНАО</strong><span>{loading ? "Загружаем материалы…" : `${documents.length.toLocaleString("ru-RU")} материалов`}</span></div>
        <button className="help-button" aria-label="Помощь" onClick={() => setView("help")}><Icon name="help" /></button>
      </header>

      {view === "search" && <>
        <section className={`hero ${submittedQuery ? "hero-compact" : ""}`}>
          <span className="eyebrow">Умный поиск</span>
          <h1>{firstName ? `${firstName}, найдём ответ?` : "Ответы по системам ЯНАО — в одном месте"}</h1>
          {!submittedQuery && <p>Опишите задачу обычными словами. Поиск проверит инструкции, базу знаний и документы.</p>}
          <form className="search-box" onSubmit={submit}>
            <span className="search-icon"><Icon name="search" /></span>
            <input ref={inputRef} aria-label="Поисковый запрос" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Например, как подписать документ?" enterKeyHint="search" />
            {query && <button type="button" className="clear-query" aria-label="Очистить запрос" onClick={() => setQuery("")}><Icon name="close" /></button>}
            <button type="submit" className="submit-search" aria-label="Найти" disabled={loading || !query.trim()}><Icon name="arrow" /></button>
          </form>
          {activeSystem && <div className="context-pill"><span>Контекст: <strong>{activeSystem.label}</strong></span><button onClick={clearContext} aria-label="Искать по всем базам"><Icon name="close" /></button></div>}
          {!submittedQuery && <div className="chips" aria-label="Популярные системы">{SYSTEMS.slice(0, 4).map((system) => <button key={system.key} onClick={() => chooseSystem(system)}>{system.label}</button>)}</div>}
        </section>

        {loadError ? <section className="status-card error-card"><strong>Не удалось загрузить базу</strong><p>Проверьте подключение к интернету и откройте мини-приложение ещё раз.</p></section>
          : submittedQuery ? <section className="results-section" aria-live="polite">
            <div className="results-meta"><strong>{results.length ? "Найдено по запросу" : "Ничего не найдено"}</strong><span>{results.length ? `${results.length} подходящих материалов` : "Уточните формулировку"}</span></div>
            <article className={`answer-card ${!results.length ? "empty-answer" : ""}`}><div className="answer-heading"><span className="spark">✦</span><div><span>Краткий ответ</span><strong>{activeSystem?.label || "По всем базам"}</strong></div></div><p>{summary}</p></article>
            {results.length > 0 && <div className="source-list">{results.map((result, index) => <button className="source-card" key={result.url} onClick={() => openResult(result.url)}><span className="source-index">{index + 1}</span><span className="source-copy"><strong>{result.title}</strong><small>{SOURCE_LABELS[result.source]}</small><p>{result.snippet}</p></span><span className="external"><Icon name="external" /></span></button>)}</div>}
          </section>
          : <section className="welcome-card"><div className="welcome-icon">✦</div><div><strong>С чего начать?</strong><p>Укажите систему и действие: «РСЭД — создать документ» или «ГИС ЕСКУ — обратиться в поддержку».</p></div></section>}
      </>}

      {view === "history" && <section className="content-view">
        <span className="eyebrow">Недавние запросы</span><h1>История поиска</h1>
        {history.length ? <div className="history-list">{history.map((item) => { const system = SYSTEMS.find((candidate) => candidate.key === item.systemKey); return <button key={`${item.createdAt}-${item.query}`} onClick={() => repeatHistory(item)}><span className="history-icon"><Icon name="history" /></span><span><strong>{item.query}</strong><small>{system?.label || "Все базы"}</small></span><Icon name="arrow" /></button>; })}</div>
          : <section className="status-card"><strong>История пока пуста</strong><p>Выполненные запросы появятся здесь и сохранятся на этом устройстве.</p></section>}
        {history.length > 0 && <button className="secondary-action" onClick={() => { setHistory([]); localStorage.removeItem(HISTORY_KEY); }}>Очистить историю</button>}
      </section>}

      {view === "help" && <section className="content-view help-view">
        <span className="eyebrow">Подсказка</span><h1>Как пользоваться</h1>
        <div className="help-card"><span>1</span><div><strong>Опишите задачу</strong><p>Напишите название системы и что хотите сделать — например: «РСЭД, согласовать документ».</p></div></div>
        <div className="help-card"><span>2</span><div><strong>Прочитайте краткий ответ</strong><p>Мини-приложение покажет выдержку из наиболее подходящей инструкции.</p></div></div>
        <div className="help-card"><span>3</span><div><strong>Откройте источник</strong><p>Нажмите на карточку, чтобы перейти к полной инструкции или документу.</p></div></div>
        <div className="privacy-note"><Icon name="book" /><p>Поиск выполняется по материалам РСЭД, ГИС ЕСКУ, базе знаний и документам ЯНАО. История хранится только на вашем устройстве.</p></div>
      </section>}

      <nav className="bottom-nav" aria-label="Навигация">
        <button className={view === "search" ? "active" : ""} onClick={() => setView("search")}><Icon name="search" />Поиск</button>
        <button className={view === "history" ? "active" : ""} onClick={() => setView("history")}><Icon name="history" />История</button>
        <button className={view === "help" ? "active" : ""} onClick={() => setView("help")}><Icon name="help" />Помощь</button>
      </nav>
    </main>
  );
}
