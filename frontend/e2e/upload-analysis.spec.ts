import { Buffer } from 'node:buffer'

import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const session = {
  id: 'browser-session',
  created_at: '2026-08-27T10:00:00Z',
  expires_at: '2026-08-27T10:30:00Z',
  cue_count: 1,
  duration_ms: 120_000,
  warnings: [],
}

test('upload, timing preview, and ranked analysis work in a browser', async ({
  page,
}) => {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/capabilities') {
      await route.fulfill({
        json: {
          upload: true,
          live_analyzer: false,
          subtitle_provider: false,
          provider_name: null,
          provider_attribution: null,
        },
      })
    } else if (url.pathname.endsWith('/upload')) {
      await route.fulfill({ status: 201, json: session })
    } else if (url.pathname.endsWith('/preview')) {
      await route.fulfill({
        json: {
          session_id: session.id,
          at_ms: 60_000,
          sync_offset_ms: 250,
          cues: [
            {
              id: 'cue-1',
              start_ms: 60_250,
              end_ms: 62_250,
              text: "Let's call it a day.",
              flags: [],
            },
          ],
        },
      })
    } else if (url.pathname === '/api/v1/analyses') {
      await route.fulfill({
        json: {
          id: 'analysis-1',
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
              contextual_meaning: 'finish now',
              pronunciation: null,
              pronunciation_notation: null,
              estimated_cefr: 'B2',
              confidence: 0.9,
              relevance_score: 0.9,
              usage_note: 'Informal.',
              occurrences: [
                {
                  cue_id: 'cue-1',
                  start_ms: 60_250,
                  end_ms: 62_250,
                  context_excerpt: "Let's call it a day.",
                },
              ],
            },
          ],
          warnings: [],
          provenance: {
            analyzer_name: 'offline-browser-fixture',
            model_identifier: 'fixture-v1',
            prompt_version: 'prompt-v1',
            schema_version: 'schema-v1',
            grounding_version: 'grounding-v1',
            ranking_version: 'ranking-v2',
            latency_ms: 1,
            input_tokens: null,
            output_tokens: null,
          },
          created_at: '2026-08-27T10:00:01Z',
        },
      })
    } else {
      await route.fulfill({ status: 204 })
    }
  })

  await page.goto('/')
  const initialAccessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(initialAccessibility.violations).toEqual([])
  await page.getByLabel('English SRT file').setInputFiles({
    name: 'synthetic.srt',
    mimeType: 'application/x-subrip',
    buffer: Buffer.from(
      "1\n00:01:00,000 --> 00:01:02,000\nLet's call it a day.\n",
    ),
  })
  await page.getByLabel('I have the right to use this subtitle file.').check()
  await page.getByRole('button', { name: 'Prepare subtitle' }).click()
  await expect(page.getByText(/Subtitle ready: 1 cue/)).toBeVisible()

  await page.getByLabel('Sync offset (milliseconds)').fill('250')
  await page.getByRole('button', { name: 'Show nearby cues' }).click()
  await expect(page.getByText("Let's call it a day.")).toBeVisible()

  await page.getByLabel('Your English level').selectOption('B1')
  await page.getByRole('button', { name: 'Build my study list' }).click()
  await expect(page.getByRole('heading', { name: 'Your study list' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'call it a day' })).toBeVisible()
  await expect(page.getByRole('status')).toBeFocused()
  const resultAccessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(resultAccessibility.violations).toEqual([])
})
