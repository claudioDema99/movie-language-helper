import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, HttpApiClient } from './client'

describe('HttpApiClient', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('maps the stable error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'session_expired',
              message: 'Session expired.',
              retryable: false,
              correlation_id: 'request-1',
            },
          }),
          { status: 410, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const client = new HttpApiClient('/backend')
    await expect(client.previewTranscript('id', 1000, 0)).rejects.toMatchObject({
      code: 'session_expired',
      correlationId: 'request-1',
      status: 410,
    } satisfies Partial<ApiError>)
  })

  it('uses no-store and safely maps non-contract failures', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('upstream detail', { status: 502 }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new HttpApiClient()
    await expect(
      client.analyze({
        transcript_session_id: 'id',
        start_ms: 0,
        end_ms: 1000,
        sync_offset_ms: 0,
        cefr_level: 'B1',
      }),
    ).rejects.toMatchObject({ code: 'unexpected_response', retryable: true })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/analyses',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('wraps network failures and supports deletion', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('private network detail'))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new HttpApiClient()
    await expect(client.uploadTranscript(new File(['x'], 'x.srt'))).rejects.toMatchObject(
      { code: 'network_error', retryable: true },
    )
    await expect(client.deleteTranscript('id')).resolves.toBeUndefined()
  })

  it('maps capability and provider endpoint requests', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ upload: true })))
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'session' })))
    vi.stubGlobal('fetch', fetchMock)
    const client = new HttpApiClient()
    await client.getCapabilities()
    await client.searchMovies('Synthetic', 2020)
    await client.listSubtitles('movie/id')
    await client.createProviderSession('subtitle-1')
    expect(fetchMock.mock.calls.at(1)?.[0]).toBe(
      '/api/v1/movies?q=Synthetic&year=2020',
    )
    expect(fetchMock.mock.calls.at(2)?.[0]).toBe(
      '/api/v1/movies/movie%2Fid/subtitles',
    )
    expect(fetchMock.mock.calls.at(3)?.[1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ subtitle_id: 'subtitle-1' }),
      }),
    )
  })
})
