import type {
  AnalysisRequest,
  AnalysisResult,
  ApiErrorBody,
  Capabilities,
  MovieMatch,
  SubtitleCandidate,
  TranscriptPreview,
  TranscriptSession,
} from './types'

const DEFAULT_TIMEOUT_MS = 25_000

export class ApiError extends Error {
  readonly code: string
  readonly retryable: boolean
  readonly correlationId: string
  readonly status: number

  constructor(
    message: string,
    options: {
      code: string
      retryable: boolean
      correlationId: string
      status: number
    },
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.retryable = options.retryable
    this.correlationId = options.correlationId
    this.status = options.status
  }
}

export interface ApiClient {
  getCapabilities(signal?: AbortSignal): Promise<Capabilities>
  searchMovies(
    query: string,
    year?: number,
    signal?: AbortSignal,
  ): Promise<MovieMatch[]>
  listSubtitles(movieId: string, signal?: AbortSignal): Promise<SubtitleCandidate[]>
  createProviderSession(
    subtitleId: string,
    signal?: AbortSignal,
  ): Promise<TranscriptSession>
  uploadTranscript(file: File, signal?: AbortSignal): Promise<TranscriptSession>
  previewTranscript(
    sessionId: string,
    atMs: number,
    syncOffsetMs: number,
    signal?: AbortSignal,
  ): Promise<TranscriptPreview>
  analyze(
    request: AnalysisRequest,
    signal?: AbortSignal,
  ): Promise<AnalysisResult>
  deleteTranscript(sessionId: string, signal?: AbortSignal): Promise<void>
}

export class HttpApiClient implements ApiClient {
  constructor(
    private readonly baseUrl = '',
    private readonly timeoutMs = DEFAULT_TIMEOUT_MS,
  ) {}

  async getCapabilities(signal?: AbortSignal): Promise<Capabilities> {
    return this.request('/api/v1/capabilities', { signal })
  }

  async searchMovies(
    query: string,
    year?: number,
    signal?: AbortSignal,
  ): Promise<MovieMatch[]> {
    const params = new URLSearchParams({ q: query })
    if (year !== undefined) params.set('year', String(year))
    return this.request(`/api/v1/movies?${params}`, { signal })
  }

  async listSubtitles(
    movieId: string,
    signal?: AbortSignal,
  ): Promise<SubtitleCandidate[]> {
    return this.request(
      `/api/v1/movies/${encodeURIComponent(movieId)}/subtitles`,
      { signal },
    )
  }

  async createProviderSession(
    subtitleId: string,
    signal?: AbortSignal,
  ): Promise<TranscriptSession> {
    return this.request('/api/v1/transcript-sessions/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subtitle_id: subtitleId }),
      signal,
    })
  }

  async uploadTranscript(
    file: File,
    signal?: AbortSignal,
  ): Promise<TranscriptSession> {
    const body = new FormData()
    body.append('file', file)
    body.append('rights_acknowledged', 'true')
    return this.request('/api/v1/transcript-sessions/upload', {
      method: 'POST',
      body,
      signal,
    })
  }

  async previewTranscript(
    sessionId: string,
    atMs: number,
    syncOffsetMs: number,
    signal?: AbortSignal,
  ): Promise<TranscriptPreview> {
    const query = new URLSearchParams({
      at_ms: String(atMs),
      sync_offset_ms: String(syncOffsetMs),
    })
    return this.request(
      `/api/v1/transcript-sessions/${encodeURIComponent(sessionId)}/preview?${query}`,
      { signal },
    )
  }

  async analyze(
    request: AnalysisRequest,
    signal?: AbortSignal,
  ): Promise<AnalysisResult> {
    return this.request('/api/v1/analyses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    })
  }

  async deleteTranscript(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<void> {
    await this.request(
      `/api/v1/transcript-sessions/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE', signal },
      false,
    )
  }

  private async request<T>(
    path: string,
    init: RequestInit,
    expectsJson = true,
  ): Promise<T> {
    const timeoutController = new AbortController()
    const timeout = window.setTimeout(
      () => timeoutController.abort(new DOMException('Request timed out', 'TimeoutError')),
      this.timeoutMs,
    )
    const signal = init.signal
      ? AbortSignal.any([init.signal, timeoutController.signal])
      : timeoutController.signal
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        cache: 'no-store',
        credentials: 'same-origin',
        signal,
      })
      if (!response.ok) {
        throw await this.toApiError(response)
      }
      if (!expectsJson || response.status === 204) {
        return undefined as T
      }
      return (await response.json()) as T
    } catch (error) {
      if (error instanceof ApiError || error instanceof DOMException) {
        throw error
      }
      throw new ApiError('The server could not be reached.', {
        code: 'network_error',
        retryable: true,
        correlationId: 'unavailable',
        status: 0,
      })
    } finally {
      window.clearTimeout(timeout)
    }
  }

  private async toApiError(response: Response): Promise<ApiError> {
    try {
      const body = (await response.json()) as ApiErrorBody
      if (body.error && typeof body.error.code === 'string') {
        return new ApiError(body.error.message, {
          code: body.error.code,
          retryable: body.error.retryable,
          correlationId: body.error.correlation_id,
          status: response.status,
        })
      }
    } catch {
      // The stable fallback below intentionally hides non-contract response bodies.
    }
    return new ApiError('The server returned an unexpected response.', {
      code: 'unexpected_response',
      retryable: response.status >= 500,
      correlationId: response.headers.get('X-Request-ID') ?? 'unavailable',
      status: response.status,
    })
  }
}

export const apiClient = new HttpApiClient()
