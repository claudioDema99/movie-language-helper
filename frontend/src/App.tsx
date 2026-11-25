import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from 'react'

import { ApiError, apiClient, type ApiClient } from './api/client'
import type {
  AnalysisResult,
  Capabilities,
  CefrLevel,
  MovieMatch,
  SubtitleCandidate,
  TranscriptPreview,
  TranscriptSession,
} from './api/types'

type PendingAction =
  | 'upload'
  | 'movie search'
  | 'subtitle search'
  | 'provider download'
  | 'preview'
  | 'analysis'
  | null

const UPLOAD_ONLY_CAPABILITIES: Capabilities = {
  upload: true,
  live_analyzer: false,
  subtitle_provider: false,
  provider_name: null,
  provider_attribution: null,
}

interface AppProps {
  client?: ApiClient
}

interface UiError {
  message: string
  retryable: boolean
  correlationId?: string
}

function secondsToMilliseconds(value: string): number {
  return Math.round(Number(value) * 1000)
}

function formatTimestamp(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours, minutes, seconds]
    .map((part) => String(part).padStart(2, '0'))
    .join(':')
}

function describeError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return {
      message:
        error.code === 'session_expired'
          ? 'This transcript session expired. Upload the subtitle again to continue.'
          : error.message,
      retryable: error.retryable,
      correlationId: error.correlationId,
    }
  }
  if (error instanceof DOMException && error.name === 'AbortError') {
    return { message: 'The request was cancelled.', retryable: true }
  }
  return {
    message: 'Something unexpected happened. Please try again.',
    retryable: true,
  }
}

export function App({ client = apiClient }: AppProps) {
  const [file, setFile] = useState<File | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [rightsAcknowledged, setRightsAcknowledged] = useState(false)
  const [session, setSession] = useState<TranscriptSession | null>(null)
  const [preview, setPreview] = useState<TranscriptPreview | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [previewAtSeconds, setPreviewAtSeconds] = useState('60')
  const [syncOffsetMs, setSyncOffsetMs] = useState('0')
  const [startSeconds, setStartSeconds] = useState('60')
  const [endSeconds, setEndSeconds] = useState('120')
  const [cefrLevel, setCefrLevel] = useState<CefrLevel>('unspecified')
  const [pending, setPending] = useState<PendingAction>(null)
  const [error, setError] = useState<UiError | null>(null)
  const [validationMessage, setValidationMessage] = useState('')
  const [movieQuery, setMovieQuery] = useState('')
  const [movieYear, setMovieYear] = useState('')
  const [movies, setMovies] = useState<MovieMatch[]>([])
  const [movieSearchComplete, setMovieSearchComplete] = useState(false)
  const [selectedMovie, setSelectedMovie] = useState<MovieMatch | null>(null)
  const [subtitles, setSubtitles] = useState<SubtitleCandidate[]>([])
  const statusRef = useRef<HTMLDivElement>(null)
  const requestController = useRef<AbortController | null>(null)

  useEffect(() => {
    if (session || error || validationMessage || analysis) {
      statusRef.current?.focus()
    }
  }, [analysis, error, session, validationMessage])

  useEffect(() => {
    const controller = new AbortController()
    client
      .getCapabilities(controller.signal)
      .then(setCapabilities)
      .catch(() => setCapabilities(UPLOAD_ONLY_CAPABILITIES))
    return () => controller.abort()
  }, [client])

  useEffect(
    () => () => {
      requestController.current?.abort()
    },
    [],
  )

  function beginRequest(action: Exclude<PendingAction, null>): AbortSignal {
    requestController.current?.abort()
    const controller = new AbortController()
    requestController.current = controller
    setPending(action)
    setError(null)
    setValidationMessage('')
    return controller.signal
  }

  function finishRequest(): void {
    requestController.current = null
    setPending(null)
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!file || !rightsAcknowledged) {
      setValidationMessage(
        'Choose an English SRT file and confirm that you have the right to use it.',
      )
      return
    }
    const signal = beginRequest('upload')
    try {
      const created = await client.uploadTranscript(file, signal)
      await adoptSession(created, signal)
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  async function adoptSession(
    created: TranscriptSession,
    signal: AbortSignal,
  ): Promise<void> {
    const previous = session
    setSession(created)
    setPreview(null)
    setAnalysis(null)
    if (previous && previous.id !== created.id) {
      await client.deleteTranscript(previous.id, signal).catch(() => undefined)
    }
  }

  async function handleMovieSearch(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()
    const query = movieQuery.trim()
    const year = movieYear === '' ? undefined : Number(movieYear)
    if (query.length < 2 || (year !== undefined && !Number.isInteger(year))) {
      setValidationMessage('Enter at least two title characters and a valid year.')
      return
    }
    const signal = beginRequest('movie search')
    setMovieSearchComplete(false)
    try {
      setMovies(await client.searchMovies(query, year, signal))
      setMovieSearchComplete(true)
      setSelectedMovie(null)
      setSubtitles([])
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  async function chooseMovie(movie: MovieMatch): Promise<void> {
    const signal = beginRequest('subtitle search')
    setSelectedMovie(movie)
    setSubtitles([])
    try {
      setSubtitles(await client.listSubtitles(movie.id, signal))
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  async function chooseSubtitle(candidate: SubtitleCandidate): Promise<void> {
    const signal = beginRequest('provider download')
    try {
      const created = await client.createProviderSession(candidate.id, signal)
      await adoptSession(created, signal)
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!session) return
    const atMs = secondsToMilliseconds(previewAtSeconds)
    const offset = Number(syncOffsetMs)
    if (!Number.isInteger(atMs) || atMs < 0 || !Number.isInteger(offset)) {
      setValidationMessage('Preview time and offset must be valid numbers.')
      return
    }
    const signal = beginRequest('preview')
    try {
      setPreview(await client.previewTranscript(session.id, atMs, offset, signal))
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  async function handleAnalysis(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!session) return
    const startMs = secondsToMilliseconds(startSeconds)
    const endMs = secondsToMilliseconds(endSeconds)
    const offset = Number(syncOffsetMs)
    if (
      !Number.isInteger(startMs) ||
      !Number.isInteger(endMs) ||
      startMs < 0 ||
      endMs <= startMs ||
      endMs - startMs > 600_000 ||
      !Number.isInteger(offset)
    ) {
      setValidationMessage(
        'Choose an interval longer than zero and no more than 10 minutes.',
      )
      return
    }
    const signal = beginRequest('analysis')
    try {
      setAnalysis(
        await client.analyze(
          {
            transcript_session_id: session.id,
            start_ms: startMs,
            end_ms: endMs,
            sync_offset_ms: offset,
            cefr_level: cefrLevel,
          },
          signal,
        ),
      )
    } catch (caught) {
      setError(describeError(caught))
    } finally {
      finishRequest()
    }
  }

  function invalidateTiming(event: ChangeEvent<HTMLInputElement>): void {
    setSyncOffsetMs(event.target.value)
    setPreview(null)
    setAnalysis(null)
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">Scene preparation for English learners</p>
        <h1>Understand the scene before you press play.</h1>
        <p className="hero-copy">
          Upload an English subtitle, check its timing, and get a short study
          list for the part of the movie you plan to watch.
        </p>
      </header>

      <div
        ref={statusRef}
        className="status-region"
        role="status"
        aria-live="polite"
        tabIndex={-1}
      >
        {pending && <p>Working: {pending}…</p>}
        {validationMessage && <p className="message error">{validationMessage}</p>}
        {error && (
          <div className="message error" role="alert">
            <p>{error.message}</p>
            {error.retryable && <p>You can safely try this step again.</p>}
            {error.correlationId && error.correlationId !== 'unavailable' && (
              <p className="technical-note">Reference: {error.correlationId}</p>
            )}
          </div>
        )}
        {session && !pending && !error && (
          <p className="message success">
            Subtitle ready: {session.cue_count.toLocaleString()} cues, ending at{' '}
            {formatTimestamp(session.duration_ms)}. This session expires at{' '}
            {new Date(session.expires_at).toLocaleTimeString()}.
          </p>
        )}
      </div>

      <section className="workflow-grid" aria-label="Study workflow">
        <article className="panel upload-panel">
          <div className="step-heading">
            <span>01</span>
            <div>
              <p className="kicker">Subtitle</p>
              <h2>Start with your SRT</h2>
            </div>
          </div>
          <form onSubmit={handleUpload}>
            <label htmlFor="subtitle-file">English SRT file</label>
            <input
              id="subtitle-file"
              type="file"
              accept=".srt,application/x-subrip,text/plain"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setSession(null)
                setPreview(null)
                setAnalysis(null)
              }}
            />
            <label className="check-row">
              <input
                type="checkbox"
                checked={rightsAcknowledged}
                onChange={(event) => setRightsAcknowledged(event.target.checked)}
              />
              <span>I have the right to use this subtitle file.</span>
            </label>
            <button type="submit" disabled={pending !== null}>
              {pending === 'upload' ? 'Uploading…' : 'Prepare subtitle'}
            </button>
          </form>
          {capabilities?.subtitle_provider && (
            <div className="provider-flow">
              <div className="choice-divider"><span>or find a release</span></div>
              <form onSubmit={handleMovieSearch}>
                <div className="field-pair">
                  <label>
                    Movie title
                    <input
                      value={movieQuery}
                      minLength={2}
                      maxLength={200}
                      onChange={(event) => {
                        setMovieQuery(event.target.value)
                        setMovieSearchComplete(false)
                      }}
                    />
                  </label>
                  <label>
                    Year (optional)
                    <input
                      type="number"
                      min="1870"
                      max="2200"
                      value={movieYear}
                      onChange={(event) => {
                        setMovieYear(event.target.value)
                        setMovieSearchComplete(false)
                      }}
                    />
                  </label>
                </div>
                <button type="submit" disabled={pending !== null}>
                  {pending === 'movie search' ? 'Searching…' : 'Search movies'}
                </button>
              </form>
              {movies.length === 0 && movieSearchComplete && pending === null && (
                <p className="technical-note">
                  No movie matches were found. Try a broader title or remove the year.
                </p>
              )}
              {movies.length > 0 && (
                <ul className="provider-list" aria-label="Movie matches">
                  {movies.map((movie) => (
                    <li key={movie.id}>
                      <button type="button" onClick={() => void chooseMovie(movie)}>
                        {movie.title}{movie.year ? ` (${movie.year})` : ''}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {selectedMovie && subtitles.length === 0 && pending === null && (
                <p className="technical-note">
                  No English subtitle releases were found. Upload your own SRT instead.
                </p>
              )}
              {subtitles.length > 0 && (
                <div>
                  <p className="release-guidance">
                    Choose the release closest to your video. A mismatch can cause a
                    constant offset or timing drift; verify it in step 2.
                  </p>
                  <ul className="provider-list" aria-label="English subtitle releases">
                    {subtitles.map((candidate) => (
                      <li key={candidate.id}>
                        <button
                          type="button"
                          onClick={() => void chooseSubtitle(candidate)}
                        >
                          <strong>{candidate.release_name}</strong>
                          <span>
                            {candidate.format?.toUpperCase() ?? 'format unknown'}
                            {candidate.fps ? ` · ${candidate.fps} FPS` : ''}
                            {candidate.hearing_impaired === true ? ' · HI' : ''}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="provider-disclosure">
                {capabilities.provider_attribution} Provider subtitles are processed
                only in the transient session described below. See the{' '}
                <a href="https://subdl.com/terms" rel="noreferrer" target="_blank">
                  SubDL terms
                </a>{' '}
                and this deployment’s privacy notice before use.
              </p>
            </div>
          )}
        </article>

        <article className={`panel ${session ? '' : 'panel-disabled'}`}>
          <div className="step-heading">
            <span>02</span>
            <div>
              <p className="kicker">Synchronization</p>
              <h2>Check the timing</h2>
            </div>
          </div>
          <p className="panel-copy">
            A positive offset shows subtitles later; a negative offset shows
            them earlier. It corrects a constant shift, not progressive drift.
          </p>
          <form onSubmit={handlePreview}>
            <div className="field-pair">
              <label>
                Playback time (seconds)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={previewAtSeconds}
                  disabled={!session}
                  onChange={(event) => {
                    setPreviewAtSeconds(event.target.value)
                    setPreview(null)
                  }}
                />
              </label>
              <label>
                Sync offset (milliseconds)
                <input
                  type="number"
                  min="-600000"
                  max="600000"
                  step="1"
                  value={syncOffsetMs}
                  disabled={!session}
                  onChange={invalidateTiming}
                />
              </label>
            </div>
            <button type="submit" disabled={!session || pending !== null}>
              {pending === 'preview' ? 'Checking…' : 'Show nearby cues'}
            </button>
          </form>
          {preview && (
            <ol className="cue-list" aria-label="Subtitle timing preview">
              {preview.cues.length === 0 && <li>No nearby dialogue cues.</li>}
              {preview.cues.map((cue) => (
                <li key={cue.id}>
                  <time>{formatTimestamp(cue.start_ms)}</time>
                  <span>{cue.text}</span>
                </li>
              ))}
            </ol>
          )}
        </article>

        <article className={`panel analysis-panel ${session ? '' : 'panel-disabled'}`}>
          <div className="step-heading">
            <span>03</span>
            <div>
              <p className="kicker">Study list</p>
              <h2>Choose the scene</h2>
            </div>
          </div>
          <form onSubmit={handleAnalysis}>
            <div className="field-row">
              <label>
                Start (seconds)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={startSeconds}
                  disabled={!session}
                  onChange={(event) => {
                    setStartSeconds(event.target.value)
                    setAnalysis(null)
                  }}
                />
              </label>
              <label>
                End (seconds)
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={endSeconds}
                  disabled={!session}
                  onChange={(event) => {
                    setEndSeconds(event.target.value)
                    setAnalysis(null)
                  }}
                />
              </label>
              <label>
                Your English level
                <select
                  value={cefrLevel}
                  disabled={!session}
                  onChange={(event) => {
                    setCefrLevel(event.target.value as CefrLevel)
                    setAnalysis(null)
                  }}
                >
                  <option value="unspecified">Not specified</option>
                  {(['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] as const).map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button type="submit" disabled={!session || pending !== null}>
              {pending === 'analysis' ? 'Analyzing…' : 'Build my study list'}
            </button>
          </form>
        </article>
      </section>

      {analysis && (
        <section className="results" aria-labelledby="results-title">
          <div className="results-heading">
            <div>
              <p className="eyebrow">Ranked for this scene</p>
              <h2 id="results-title">Your study list</h2>
            </div>
            <p>{analysis.items.length} useful items</p>
          </div>
          {analysis.items.length === 0 ? (
            <p className="empty-state">
              No grounded learning items were found for this interval. Try a
              longer scene or a different learner level.
            </p>
          ) : (
            <ol className="item-list">
              {analysis.items.map((item) => (
                <li key={item.id} className="learning-card">
                  <div className="item-title-row">
                    <div>
                      <p className="item-type">{item.type.replace('_', ' ')}</p>
                      <h3>{item.expression}</h3>
                    </div>
                    <span className="score">
                      {Math.round(item.relevance_score * 100)} relevance
                    </span>
                  </div>
                  <dl>
                    <div>
                      <dt>General meaning</dt>
                      <dd>{item.general_meaning}</dd>
                    </div>
                    <div>
                      <dt>In this scene</dt>
                      <dd>{item.contextual_meaning}</dd>
                    </div>
                    {item.estimated_cefr && (
                      <div>
                        <dt>Estimated level</dt>
                        <dd>
                          {item.estimated_cefr}
                          {item.confidence !== null &&
                            ` · ${Math.round(item.confidence * 100)}% confidence`}
                        </dd>
                      </div>
                    )}
                    {item.pronunciation && (
                      <div>
                        <dt>Pronunciation ({item.pronunciation_notation})</dt>
                        <dd>{item.pronunciation}</dd>
                      </div>
                    )}
                  </dl>
                  {item.occurrences.map((occurrence) => (
                    <blockquote key={`${item.id}-${occurrence.cue_id}`}>
                      <time>{formatTimestamp(occurrence.start_ms)}</time>
                      <p>{occurrence.context_excerpt}</p>
                    </blockquote>
                  ))}
                  {item.usage_note && <p className="usage-note">{item.usage_note}</p>}
                </li>
              ))}
            </ol>
          )}
          <p className="provenance">
            Generated by {analysis.provenance.analyzer_name} using{' '}
            {analysis.provenance.model_identifier}. Explanations and level
            estimates can be wrong; use them as preparation, not authority.
          </p>
        </section>
      )}

      <footer>
        <p>
          Movie Language Helper does not play movies or export transcripts.
          Uploaded subtitles are held in a short-lived local session.
        </p>
      </footer>
    </main>
  )
}
