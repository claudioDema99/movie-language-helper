import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { ApiError, type ApiClient } from './api/client'
import type { AnalysisResult, TranscriptSession } from './api/types'

afterEach(cleanup)

const session: TranscriptSession = {
  id: 'session-test',
  created_at: '2026-08-26T12:00:00Z',
  expires_at: '2026-08-26T12:30:00Z',
  cue_count: 2,
  duration_ms: 180_000,
  warnings: [],
}

const analysis: AnalysisResult = {
  id: 'analysis-test',
  transcript_session_id: session.id,
  start_ms: 60_000,
  end_ms: 120_000,
  sync_offset_ms: 250,
  cefr_level: 'B1',
  item_limit: 12,
  items: [
    {
      id: 'item-1',
      expression: 'call it a day',
      normalized_form: 'call it a day',
      type: 'idiom',
      general_meaning: 'stop an activity',
      contextual_meaning: 'finish working now',
      pronunciation: 'call-it-a-day',
      pronunciation_notation: 'respelling',
      estimated_cefr: 'B2',
      confidence: 0.9,
      relevance_score: 0.87,
      usage_note: 'Informal.',
      occurrences: [
        {
          cue_id: 'cue-1',
          start_ms: 61_250,
          end_ms: 63_250,
          context_excerpt: "Let's call it a day.",
        },
      ],
    },
  ],
  warnings: [],
  provenance: {
    analyzer_name: 'offline-fake',
    model_identifier: 'fixture-v1',
    prompt_version: 'prompt-v1',
    schema_version: 'schema-v1',
    grounding_version: 'grounding-v1',
    ranking_version: 'ranking-v2',
    latency_ms: 1,
    input_tokens: null,
    output_tokens: null,
  },
  created_at: '2026-08-26T12:00:01Z',
}

function fakeClient(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    getCapabilities: vi.fn().mockResolvedValue({
      upload: true,
      live_analyzer: false,
      subtitle_provider: false,
      provider_name: null,
      provider_attribution: null,
    }),
    searchMovies: vi.fn().mockResolvedValue([]),
    listSubtitles: vi.fn().mockResolvedValue([]),
    createProviderSession: vi.fn().mockResolvedValue(session),
    uploadTranscript: vi.fn().mockResolvedValue(session),
    previewTranscript: vi.fn().mockResolvedValue({
      session_id: session.id,
      at_ms: 60_000,
      sync_offset_ms: 250,
      cues: [
        {
          id: 'cue-1',
          start_ms: 61_250,
          end_ms: 63_250,
          text: "Let's call it a day.",
          flags: [],
        },
      ],
    }),
    analyze: vi.fn().mockResolvedValue(analysis),
    deleteTranscript: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

async function uploadSubtitle(client: ApiClient): Promise<void> {
  render(<App client={client} />)
  const input = screen.getByLabelText('English SRT file')
  fireEvent.change(input, {
    target: { files: [new File(['synthetic'], 'synthetic.srt')] },
  })
  fireEvent.click(
    screen.getByRole('checkbox', {
      name: 'I have the right to use this subtitle file.',
    }),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Prepare subtitle' }))
  await screen.findByText(/Subtitle ready: 2 cues/)
}

describe('App', () => {
  it('renders the accessible provider-free workflow', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        name: 'Understand the scene before you press play.',
      }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('English SRT file')).toHaveAttribute(
      'accept',
      expect.stringContaining('.srt'),
    )
    expect(screen.getByRole('button', { name: 'Show nearby cues' })).toBeDisabled()
  })

  it('validates rights acknowledgement before uploading', () => {
    render(<App client={fakeClient()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Prepare subtitle' }))
    expect(screen.getByRole('status')).toHaveFocus()
    expect(screen.getByText(/Choose an English SRT file/)).toBeInTheDocument()
  })

  it('completes upload, timing preview, and analysis with a fake backend', async () => {
    const client = fakeClient()
    await uploadSubtitle(client)

    fireEvent.change(screen.getByLabelText('Sync offset (milliseconds)'), {
      target: { value: '250' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Show nearby cues' }))
    expect(await screen.findByText("Let's call it a day.")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Your English level'), {
      target: { value: 'B1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Build my study list' }))
    expect(await screen.findByRole('heading', { name: 'Your study list' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveFocus()
    expect(screen.getByRole('heading', { name: 'call it a day' })).toBeInTheDocument()
    expect(screen.getByText('B2 · 90% confidence')).toBeInTheDocument()
    expect(client.analyze).toHaveBeenCalledWith(
      expect.objectContaining({
        transcript_session_id: session.id,
        sync_offset_ms: 250,
        cefr_level: 'B1',
      }),
      expect.any(AbortSignal),
    )
  })

  it('shows an actionable expired-session error', async () => {
    const client = fakeClient({
      previewTranscript: vi.fn().mockRejectedValue(
        new ApiError('expired', {
          code: 'session_expired',
          retryable: false,
          correlationId: 'request-1',
          status: 410,
        }),
      ),
    })
    await uploadSubtitle(client)
    fireEvent.click(screen.getByRole('button', { name: 'Show nearby cues' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Upload the subtitle again')
    expect(alert).toHaveTextContent('Reference: request-1')
  })

  it('invalidates results when timing changes', async () => {
    await uploadSubtitle(fakeClient())
    fireEvent.click(screen.getByRole('button', { name: 'Build my study list' }))
    await screen.findByRole('heading', { name: 'Your study list' })
    fireEvent.change(screen.getByLabelText('Sync offset (milliseconds)'), {
      target: { value: '-500' },
    })
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Your study list' })).toBeNull()
    })
  })

  it('supports capability-gated movie and subtitle selection', async () => {
    const providerSession = { ...session, id: 'provider-session' }
    const client = fakeClient({
      getCapabilities: vi.fn().mockResolvedValue({
        upload: true,
        live_analyzer: true,
        subtitle_provider: true,
        provider_name: 'SubDL',
        provider_attribution: 'Provided by SubDL.',
      }),
      searchMovies: vi.fn().mockResolvedValue([
        { provider: 'subdl', id: '42', title: 'Synthetic Movie', year: 2020 },
      ]),
      listSubtitles: vi.fn().mockResolvedValue([
        {
          provider: 'subdl',
          id: '7',
          movie_id: '42',
          release_name: 'Synthetic.1080p',
          language: 'en',
          hearing_impaired: false,
          format: 'srt',
          fps: 24,
        },
      ]),
      createProviderSession: vi.fn().mockResolvedValue(providerSession),
    })
    render(<App client={client} />)
    expect(await screen.findByLabelText('Movie title')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Movie title'), {
      target: { value: 'Synthetic' },
    })
    fireEvent.change(screen.getByLabelText('Year (optional)'), {
      target: { value: '2020' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search movies' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Synthetic Movie (2020)' }))
    const release = await screen.findByRole('button', {
      name: /Synthetic.1080p.*SRT.*24 FPS/,
    })
    fireEvent.click(release)
    expect(await screen.findByText(/Subtitle ready: 2 cues/)).toBeInTheDocument()
    expect(client.createProviderSession).toHaveBeenCalledWith(
      '7',
      expect.any(AbortSignal),
    )
    expect(screen.getByText(/release closest to your video/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SubDL terms' })).toHaveAttribute(
      'href',
      'https://subdl.com/terms',
    )
  })
})
