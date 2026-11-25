export type CefrLevel =
  | 'A1'
  | 'A2'
  | 'B1'
  | 'B2'
  | 'C1'
  | 'C2'
  | 'unspecified'

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    retryable: boolean
    correlation_id: string
  }
}

export interface TranscriptSession {
  id: string
  created_at: string
  expires_at: string
  cue_count: number
  duration_ms: number
  warnings: string[]
}

export interface PreviewCue {
  id: string
  start_ms: number
  end_ms: number
  text: string
  flags: string[]
}

export interface TranscriptPreview {
  session_id: string
  at_ms: number
  sync_offset_ms: number
  cues: PreviewCue[]
}

export interface Capabilities {
  upload: boolean
  live_analyzer: boolean
  subtitle_provider: boolean
  provider_name: string | null
  provider_attribution: string | null
}

export interface MovieMatch {
  provider: string
  id: string
  title: string
  year: number | null
}

export interface SubtitleCandidate {
  provider: string
  id: string
  movie_id: string
  release_name: string
  language: string
  hearing_impaired: boolean | null
  format: string | null
  fps: number | null
}

export interface AnalysisRequest {
  transcript_session_id: string
  start_ms: number
  end_ms: number
  sync_offset_ms: number
  cefr_level: CefrLevel
  item_limit?: number
}

export interface LearningItem {
  id: string
  expression: string
  normalized_form: string
  type: 'word' | 'idiom' | 'phrasal_verb' | 'slang' | 'other_expression'
  general_meaning: string
  contextual_meaning: string
  pronunciation: string | null
  pronunciation_notation: string | null
  estimated_cefr: CefrLevel | null
  confidence: number | null
  relevance_score: number
  usage_note: string | null
  occurrences: Array<{
    cue_id: string
    start_ms: number
    end_ms: number
    context_excerpt: string
  }>
}

export interface AnalysisResult extends AnalysisRequest {
  id: string
  item_limit: number
  items: LearningItem[]
  warnings: string[]
  provenance: {
    analyzer_name: string
    model_identifier: string
    prompt_version: string
    schema_version: string
    grounding_version: string
    ranking_version: string
    latency_ms: number
    input_tokens: number | null
    output_tokens: number | null
  }
  created_at: string
}
