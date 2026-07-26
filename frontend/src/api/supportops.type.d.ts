declare namespace API {
  interface SupportUploadResult {
    status: string
    message: string
    inserted: number
    skipped: number
    duplicates: number
    job_id?: number
    dataset_name?: string
    dataset_version?: string
    source_type?: string
    checksum?: string
    total_rows?: number
    pii_redacted?: number
    split_counts?: Record<string, number>
    errors: string[]
    index_result?: {
      indexed: number
      errors: string[]
    }
  }

  interface SupportUploadDocsResult {
    status: string
    message: string
    index_name: string
    successful_files: string[]
    failed_files: string[]
    indexed_chunks: number
    total_chunks: number
    chunks_before: number
    file_results: {
      file_name: string
      status: string
      parsed: number
      processed: number
      indexed: number
      errors: string[]
    }[]
  }

  interface SupportTicket {
    id: number
    instruction: string
    category: string
    intent: string
    response: string
    source: string
    source_type: string
    external_id?: string
    conversation_id?: string
    language: string
    dataset_split: string
    pii_redacted: boolean
    quality_score: number
    import_job_id?: number
    created_at: string
    updated_at: string
  }

  interface SupportDatasetImportJob {
    id: number
    dataset_name: string
    dataset_version: string
    source_filename: string
    source_type: 'real_anonymized' | 'real_derived' | 'synthetic' | 'user_provided' | 'unknown'
    status: string
    checksum: string
    total_rows: number
    accepted_rows: number
    rejected_rows: number
    duplicate_rows: number
    pii_redacted_rows: number
    indexed_rows: number
    split_counts: Record<string, number>
    import_options: Record<string, unknown>
    errors: unknown[]
    started_at: string
    completed_at?: string
  }

  interface SupportTicketsResponse {
    tickets: SupportTicket[]
    total: number
  }

  interface SupportTrace {
    id?: number
    session_id?: string
    step_order: number
    tool_name: string
    tool_input?: string | Record<string, unknown>
    tool_output?: string | Record<string, unknown>
    latency_ms: number
    status: string
    created_at?: string
  }

  interface SupportSource {
    document_id: string
    document_name: string
    content: string
    score: number
  }

  interface SupportSimilarTicket {
    id: number
    instruction: string
    category: string
    intent: string
    response: string
    score: number
  }

  interface SupportToolResult {
    tool: string
    args: Record<string, unknown>
    status: 'ok' | 'not_found' | 'missing_args' | 'error' | string
    [key: string]: unknown
  }

  interface SupportPlan {
    routes?: string[]
    tools?: { name: string; args: Record<string, unknown> }[]
    reason?: string
  }

  interface SupportFinalAnswer {
    user_question: string
    category: string
    intent: string
    risk_level: 'low' | 'medium' | 'high'
    need_human: boolean
    reply: string
    similar_tickets: SupportSimilarTicket[]
    sources: SupportSource[]
    tool_results?: SupportToolResult[]
    plan?: SupportPlan
    agent_trace: SupportTrace[]
    next_action: string
    summary?: string
    reflection?: Record<string, unknown>
    human_decision?: {
      action: 'approve' | 'edit' | 'reject'
      reviewer_note?: string
    } | null
    retry_count?: number
    workflow?: string
  }

  interface SupportSessionMessages {
    session_id: string
    messages: {
      user_question: string
      model_answer: string
      created_at: string
    }[]
  }

  interface SupportHumanReview {
    type: 'supportops_human_review'
    session_id: string
    turn_id: string
    question: string
    risk_level: 'low' | 'medium' | 'high'
    reason: string
    proposed_reply: string
    allowed_actions: ('approve' | 'edit' | 'reject')[]
  }

  interface SupportMetrics {
    ticket_total: number
    category_distribution: Record<string, number>
    intent_distribution: Record<string, number>
    risk_level_distribution: Record<string, number>
    high_risk_ratio: number
    human_transfer_ratio: number
    top_intents: {
      intent: string
      count: number
    }[]
  }

  interface SupportApiKey {
    id: number
    name: string
    provider: string
    masked_api_key: string
    base_url: string
    model: string
    embedding_model: string
    is_active: boolean
    created_at: string
    updated_at: string
  }

  interface SupportApiKeyPayload {
    name?: string
    provider?: string
    api_key?: string
    base_url?: string
    model?: string
    embedding_model?: string
    is_active?: boolean
  }

  interface SupportApiKeyTestResult {
    status: string
    chat_ok: boolean
    embedding_ok: boolean
    message: string
    details: Record<string, unknown>
  }
}
