import { AxiosRequestConfig } from 'axios'
import { request } from './request'

export function uploadTickets(
  params: { file: File },
  options?: AxiosRequestConfig,
) {
  const form = new FormData()
  form.append('file', params.file)
  return request.post<API.SupportUploadResult>('/supportops/upload_tickets', form, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    ...options,
  })
}

export function importDataset(
  params: { dataset: 'supportops_csv' | 'bitext' | 'tweetsumm' | 'msdialog'; file: File },
  options?: AxiosRequestConfig,
) {
  const form = new FormData()
  form.append('file', params.file)
  return request.post<API.SupportUploadResult>('/supportops/datasets/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { dataset: params.dataset },
    ...options,
  })
}

export function uploadDocs(
  params: { files: File[]; session_id?: string },
  options?: AxiosRequestConfig,
) {
  const form = new FormData()
  params.files.forEach((file) => form.append('files', file))
  return request.post<API.SupportUploadDocsResult>('/supportops/upload_docs', form, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    params: {
      session_id: params.session_id,
    },
    ...options,
  })
}

export function chat(
  params: { session_id: string; message: string },
  options?: AxiosRequestConfig,
) {
  const { session_id, ...body } = params
  return request.post<ReadableStream>(
    '/supportops/chat',
    body,
    {
      headers: {
        Accept: 'text/event-stream',
      },
      responseType: 'stream',
      adapter: 'fetch',
      loading: false,
      params: {
        session_id,
      },
      ...options,
    },
  )
}

export function resumeChat(
  params: {
    session_id: string
    action: 'approve' | 'edit' | 'reject'
    edited_reply?: string
    reviewer_note?: string
  },
  options?: AxiosRequestConfig,
) {
  const { session_id, ...body } = params
  return request.post<ReadableStream>('/supportops/chat/resume', body, {
    headers: { Accept: 'text/event-stream' },
    responseType: 'stream',
    adapter: 'fetch',
    loading: false,
    params: { session_id },
    ...options,
  })
}

export function pendingReview(sessionId: string, options?: AxiosRequestConfig) {
  return request.get<{ pending: boolean; review?: API.SupportHumanReview }>(
    `/supportops/reviews/${sessionId}`,
    options,
  )
}

export function sessionMessages(sessionId: string, options?: AxiosRequestConfig) {
  return request.get<API.SupportSessionMessages>(
    `/supportops/messages/${sessionId}`,
    options,
  )
}

export function workflowStatus(options?: AxiosRequestConfig) {
  return request.get<{ framework: string; backend: string; durable: boolean }>(
    '/supportops/workflow/status',
    options,
  )
}

export function tickets(options?: AxiosRequestConfig) {
  return request.get<API.SupportTicketsResponse>('/supportops/tickets', options)
}

export function updateTicket(
  id: number,
  data: { instruction: string; response: string },
  options?: AxiosRequestConfig,
) {
  return request.put<API.SupportTicketUpdateResult>(`/supportops/tickets/${id}`, data, options)
}

export function metrics(options?: AxiosRequestConfig) {
  return request.get<API.SupportMetrics>('/supportops/metrics', options)
}

export function apiKeys(options?: AxiosRequestConfig) {
  return request.get<API.SupportApiKey[]>('/supportops/api_keys', options)
}

export function createApiKey(
  data: API.SupportApiKeyPayload,
  options?: AxiosRequestConfig,
) {
  return request.post<API.SupportApiKey>('/supportops/api_keys', data, options)
}

export function updateApiKey(
  id: number,
  data: API.SupportApiKeyPayload,
  options?: AxiosRequestConfig,
) {
  return request.put<API.SupportApiKey>(`/supportops/api_keys/${id}`, data, options)
}

export function testApiKey(
  data: API.SupportApiKeyPayload,
  options?: AxiosRequestConfig,
) {
  return request.post<API.SupportApiKeyTestResult>('/supportops/api_keys/test', data, options)
}

export function testSavedApiKey(id: number, options?: AxiosRequestConfig) {
  return request.post<API.SupportApiKeyTestResult>(`/supportops/api_keys/${id}/test`, {}, options)
}

export function activateApiKey(id: number, options?: AxiosRequestConfig) {
  return request.post<API.SupportApiKey>(`/supportops/api_keys/${id}/activate`, {}, options)
}

export function deleteApiKey(id: number, options?: AxiosRequestConfig) {
  return request.delete<{ status: string; message: string }>(
    `/supportops/api_keys/${id}`,
    options,
  )
}
