import * as api from '@/api'
import {
  ApartmentOutlined,
  CheckCircleFilled,
  CloudServerOutlined,
  CommentOutlined,
  DatabaseOutlined,
  LogoutOutlined,
  MessageOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { userActions, userState } from '@/store/user'
import { Alert, Button, Empty, Input, Space, Tabs, Tag, message as antdMessage } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSnapshot } from 'valtio'
import AgentTrace from './components/AgentTrace'
import ApiKeyPanel from './components/ApiKeyPanel'
import MetricsPanel from './components/MetricsPanel'
import SourceList from './components/SourceList'
import TicketPanel from './components/TicketPanel'
import './index.module.scss'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

type ConversationHistoryItem = {
  id: string
  sessionId: string
  title: string
  messages: ChatMessage[]
  latestQuestion: string
  latestReply: string
  finalAnswer?: API.SupportFinalAnswer
  traces: API.SupportTrace[]
  sources: API.SupportSource[]
  similarTickets: API.SupportSimilarTicket[]
  status: 'pending' | 'success' | 'failed'
  turnCount: number
  createdAt: string
  updatedAt: string
}

function createSessionId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`.slice(0, 16)
}

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

const CONVERSATION_HISTORY_LIMIT = 50

function conversationHistoryStorageKey(username?: string | null) {
  return `supportops.conversation_history.${username || 'anonymous'}`
}

function normalizeChatMessages(messages: any[]): ChatMessage[] {
  return messages
    .filter((item) => item?.role === 'user' || item?.role === 'assistant')
    .map((item) => ({
      id: String(item.id || createMessageId()),
      role: item.role,
      content: String(item.content || ''),
    }))
}

function latestMessageContent(messages: ChatMessage[], role: ChatMessage['role']) {
  return [...messages].reverse().find((item) => item.role === role)?.content.trim() || ''
}

function normalizeConversationHistoryItem(item: any): ConversationHistoryItem | null {
  const finalAnswer = item?.finalAnswer || undefined
  const reply = String(item?.reply || finalAnswer?.reply || '').trim()
  const legacyQuestion = String(item?.question || item?.content || '').trim()
  const messages = Array.isArray(item?.messages)
    ? normalizeChatMessages(item.messages)
    : [
        legacyQuestion
          ? { id: createMessageId(), role: 'user' as const, content: legacyQuestion }
          : undefined,
        reply
          ? { id: createMessageId(), role: 'assistant' as const, content: reply }
          : undefined,
      ].filter((message): message is ChatMessage => Boolean(message))
  const latestQuestion = String(
    item?.latestQuestion || latestMessageContent(messages, 'user') || legacyQuestion,
  ).trim()
  if (!latestQuestion) return null

  const latestReply = String(
    item?.latestReply || latestMessageContent(messages, 'assistant') || reply,
  ).trim()
  const createdAt = String(item?.createdAt || new Date().toISOString())
  const status =
    item?.status === 'failed' || item?.status === 'pending' || item?.status === 'success'
      ? item.status
      : latestReply || finalAnswer
        ? 'success'
        : 'failed'
  const sessionId = String(item?.sessionId || item?.id || createSessionId())
  const turnCount =
    Number(item?.turnCount) ||
    messages.filter((message) => message.role === 'user' && message.content.trim()).length ||
    1

  return {
    id: sessionId,
    sessionId,
    title: String(item?.title || latestQuestion).trim(),
    messages,
    latestQuestion,
    latestReply,
    finalAnswer,
    traces: Array.isArray(item?.traces)
      ? item.traces
      : Array.isArray(finalAnswer?.agent_trace)
        ? finalAnswer.agent_trace
        : [],
    sources: Array.isArray(item?.sources)
      ? item.sources
      : Array.isArray(finalAnswer?.sources)
        ? finalAnswer.sources
        : [],
    similarTickets: Array.isArray(item?.similarTickets)
      ? item.similarTickets
      : Array.isArray(finalAnswer?.similar_tickets)
        ? finalAnswer.similar_tickets
        : [],
    status,
    turnCount,
    createdAt,
    updatedAt: String(item?.updatedAt || createdAt),
  }
}

function readConversationHistory(username?: string | null): ConversationHistoryItem[] {
  if (typeof window === 'undefined') return []

  try {
    const value = window.localStorage.getItem(conversationHistoryStorageKey(username))
    const parsed = JSON.parse(value || '[]')
    if (!Array.isArray(parsed)) return []

    return parsed
      .map(normalizeConversationHistoryItem)
      .filter((item): item is ConversationHistoryItem => Boolean(item))
      .slice(0, CONVERSATION_HISTORY_LIMIT)
  } catch {
    return []
  }
}

function writeConversationHistory(username: string | null | undefined, items: ConversationHistoryItem[]) {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(
      conversationHistoryStorageKey(username),
      JSON.stringify(items.slice(0, CONVERSATION_HISTORY_LIMIT)),
    )
  } catch {
    console.debug('SupportOps conversation history persist failed')
  }
}

function parseSseLine(line: string) {
  const data = line.trim().replace(/^data: /, '').trim()
  if (!data || data === '[DONE]') return null
  return JSON.parse(data)
}

export default function SupportOpsPage() {
  const navigate = useNavigate()
  const user = useSnapshot(userState)
  const [sessionId, setSessionId] = useState(createSessionId)
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [ticketsLoading, setTicketsLoading] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationHistory, setConversationHistory] = useState<ConversationHistoryItem[]>(() =>
    readConversationHistory(user.username),
  )
  const [traces, setTraces] = useState<API.SupportTrace[]>([])
  const [sources, setSources] = useState<API.SupportSource[]>([])
  const [similarTickets, setSimilarTickets] = useState<API.SupportSimilarTicket[]>([])
  const [finalAnswer, setFinalAnswer] = useState<API.SupportFinalAnswer>()
  const [pendingReview, setPendingReview] = useState<API.SupportHumanReview>()
  const [reviewDraft, setReviewDraft] = useState('')
  const [tickets, setTickets] = useState<API.SupportTicket[]>([])
  const [ticketTotal, setTicketTotal] = useState(0)
  const [metrics, setMetrics] = useState<API.SupportMetrics>()
  const [lastDocsUpload, setLastDocsUpload] = useState<API.SupportUploadDocsResult>()
  const [workflowStatus, setWorkflowStatus] = useState<{
    framework: string
    backend: string
    durable: boolean
  }>()

  async function refreshData() {
    setTicketsLoading(true)
    try {
      const [ticketRes, metricRes, workflowRes] = await Promise.all([
        api.supportops.tickets({ loading: false }),
        api.supportops.metrics({ loading: false }),
        api.supportops.workflowStatus({ loading: false }),
      ])
      setTickets(ticketRes.data.tickets)
      setTicketTotal(ticketRes.data.total)
      setMetrics(metricRes.data)
      setWorkflowStatus(workflowRes.data)
    } finally {
      setTicketsLoading(false)
    }
  }

  useEffect(() => {
    refreshData()
  }, [])

  useEffect(() => {
    const history = readConversationHistory(user.username)
    setConversationHistory(history)
    if (history[0]) {
      restoreConversation(history[0])
    }
  }, [user.username])

  // 客户模拟窗口（/portal）与本页共享会话记录：
  // 客户在另一个标签页提交工单时，storage 事件驱动本页实时刷新。
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === conversationHistoryStorageKey(user.username)) {
        setConversationHistory(readConversationHistory(user.username))
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [user.username])

  async function handleUploadTickets(file: File) {
    try {
      const { data } = await api.supportops.uploadTickets({ file })
      antdMessage.success(data.message)
      if (data.errors?.length) {
        antdMessage.warning(data.errors[0])
      }
      refreshData()
    } catch (error) {
      antdMessage.error((error as Error)?.message || 'CSV 上传失败')
    }
  }

  async function handleImportDataset(
    dataset: 'supportops_csv' | 'bitext' | 'tweetsumm' | 'msdialog',
    file: File,
  ) {
    try {
      const { data } = await api.supportops.importDataset({ dataset, file })
      antdMessage.success(data.message)
      if (data.errors?.length) antdMessage.warning(String(data.errors[0]))
      refreshData()
    } catch (error) {
      antdMessage.error((error as Error)?.message || '数据集导入失败')
    }
  }

  async function handleUpdateTicket(id: number, data: { instruction: string; response: string }) {
    const { data: result } = await api.supportops.updateTicket(id, data)
    antdMessage.success(`工单已更新，检索索引已重建（${result.indexed} 条）`)
    result.warnings?.forEach((warning) => antdMessage.warning(warning))
    refreshData()
  }

  async function handleUploadDocs(files: File[]) {
    try {
      const { data } = await api.supportops.uploadDocs({ files, session_id: sessionId })
      setLastDocsUpload(data)
      antdMessage.success(data.message)
      if (data.failed_files?.length) {
        antdMessage.warning(data.failed_files[0])
      }
    } catch (error) {
      antdMessage.error((error as Error)?.message || '文档上传失败')
    }
  }

  function appendAssistantContent(delta: string) {
    setMessages((prev) => {
      const next = [...prev]
      const assistant = [...next].reverse().find((item) => item.role === 'assistant')
      if (assistant) {
        assistant.content += delta
      }
      return next
    })
  }

  function handleStreamPayload(payload: any) {
    if (payload.type === 'trace' && payload.trace) {
      setTraces((prev) => [...prev, payload.trace])
      if (payload.sources) setSources(payload.sources)
      if (payload.similar_tickets) setSimilarTickets(payload.similar_tickets)
    }

    if (payload.type === 'reply_delta') {
      appendAssistantContent(payload.content || '')
    }

    if (payload.type === 'human_approval_required' && payload.approval) {
      const approval = payload.approval as API.SupportHumanReview
      setPendingReview(approval)
      setReviewDraft(approval.proposed_reply || '')
    }

    if (payload.type === 'final' && payload.final) {
      const final = payload.final as API.SupportFinalAnswer
      setFinalAnswer(final)
      setSources(final.sources || [])
      setSimilarTickets(final.similar_tickets || [])
      refreshData()
    }
  }

  async function readStream(reader: ReadableStreamDefaultReader<AllowSharedBufferSource>) {
    let temp = ''
    let streamedReply = ''
    let finalReceived = false
    let finalAnswerPayload: API.SupportFinalAnswer | undefined
    let approvalPayload: API.SupportHumanReview | undefined
    const streamTraces: API.SupportTrace[] = []
    let streamSources: API.SupportSource[] = []
    let streamSimilarTickets: API.SupportSimilarTicket[] = []
    const decoder = new TextDecoder('utf-8')
    while (true) {
      const { value, done } = await reader.read()
      temp += decoder.decode(value)

      while (true) {
        const index = temp.indexOf('\n')
        if (index === -1) break
        const line = temp.slice(0, index)
        temp = temp.slice(index + 1)
        if (!line.startsWith('data: ')) continue
        try {
          const payload = parseSseLine(line)
          if (payload?.type === 'reply_delta') streamedReply += payload.content || ''
          if (payload?.type === 'final') {
            finalReceived = true
            finalAnswerPayload = payload.final as API.SupportFinalAnswer
          }
          if (payload?.type === 'human_approval_required') {
            approvalPayload = payload.approval as API.SupportHumanReview
          }
          if (payload?.type === 'trace' && payload.trace) {
            streamTraces.push(payload.trace as API.SupportTrace)
            if (payload.sources) streamSources = payload.sources as API.SupportSource[]
            if (payload.similar_tickets) {
              streamSimilarTickets = payload.similar_tickets as API.SupportSimilarTicket[]
            }
          }
          if (payload) handleStreamPayload(payload)
        } catch {
          console.debug('SupportOps SSE parse failed', line)
        }
      }

      if (done) break
    }

    return {
      finalReceived,
      streamedReply,
      finalAnswer: finalAnswerPayload,
      approval: approvalPayload,
      traces: streamTraces,
      sources: streamSources,
      similarTickets: streamSimilarTickets,
    }
  }

  function updateConversationHistory(
    updater: (items: ConversationHistoryItem[]) => ConversationHistoryItem[],
  ) {
    setConversationHistory((prev) => {
      const next = updater(prev).slice(0, CONVERSATION_HISTORY_LIMIT)
      writeConversationHistory(user.username, next)
      return next
    })
  }

  function replaceMessageContent(items: ChatMessage[], messageId: string, content: string) {
    return items.map((item) => (item.id === messageId ? { ...item, content } : item))
  }

  function createConversationSnapshot(params: {
    sessionId: string
    messages: ChatMessage[]
    status: ConversationHistoryItem['status']
    existing?: ConversationHistoryItem
    finalAnswer?: API.SupportFinalAnswer
    traces?: API.SupportTrace[]
    sources?: API.SupportSource[]
    similarTickets?: API.SupportSimilarTicket[]
  }): ConversationHistoryItem {
    const now = new Date().toISOString()
    const normalizedMessages = normalizeChatMessages(params.messages)
    const firstQuestion =
      normalizedMessages.find((message) => message.role === 'user')?.content.trim() || '新对话'
    const latestQuestion = latestMessageContent(normalizedMessages, 'user') || firstQuestion
    const latestReply =
      params.finalAnswer?.reply ||
      latestMessageContent(normalizedMessages, 'assistant') ||
      params.existing?.latestReply ||
      ''
    const turnCount =
      normalizedMessages.filter((message) => message.role === 'user' && message.content.trim()).length ||
      1

    return {
      id: params.sessionId,
      sessionId: params.sessionId,
      title: params.existing?.title || firstQuestion,
      messages: normalizedMessages,
      latestQuestion,
      latestReply,
      finalAnswer: params.finalAnswer,
      traces: params.traces || params.finalAnswer?.agent_trace || [],
      sources: params.sources || params.finalAnswer?.sources || [],
      similarTickets: params.similarTickets || params.finalAnswer?.similar_tickets || [],
      status: params.status,
      turnCount,
      createdAt: params.existing?.createdAt || now,
      updatedAt: now,
    }
  }

  function saveConversationSession(params: {
    sessionId: string
    messages: ChatMessage[]
    status: ConversationHistoryItem['status']
    finalAnswer?: API.SupportFinalAnswer
    traces?: API.SupportTrace[]
    sources?: API.SupportSource[]
    similarTickets?: API.SupportSimilarTicket[]
  }) {
    updateConversationHistory((prev) => {
      const existing = prev.find((item) => item.sessionId === params.sessionId)
      const nextItem = createConversationSnapshot({ ...params, existing })
      return [nextItem, ...prev.filter((item) => item.sessionId !== params.sessionId)]
    })
  }

  function restoreConversation(item: ConversationHistoryItem) {
    const restoredMessages = item.messages.length
      ? item.messages
      : [
          { id: createMessageId(), role: 'user' as const, content: item.latestQuestion },
          {
            id: createMessageId(),
            role: 'assistant' as const,
            content:
              item.latestReply ||
              (item.status === 'pending' ? '处理中...' : '暂无回复内容'),
          },
        ]

    setSessionId(item.sessionId)
    setQuestion('')
    setMessages(restoredMessages)
    setTraces(item.finalAnswer?.agent_trace || item.traces || [])
    setSources(item.finalAnswer?.sources || item.sources || [])
    setSimilarTickets(item.finalAnswer?.similar_tickets || item.similarTickets || [])
    setFinalAnswer(item.finalAnswer)
    setPendingReview(undefined)
    setReviewDraft('')
    api.supportops.pendingReview(item.sessionId, { loading: false }).then(({ data }) => {
      if (data.pending && data.review) {
        setPendingReview(data.review)
        setReviewDraft(data.review.proposed_reply || '')
      }
    }).catch(() => undefined)
  }

  function startNewConversation() {
    if (loading) return
    setSessionId(createSessionId())
    setQuestion('')
    setMessages([])
    setTraces([])
    setSources([])
    setSimilarTickets([])
    setFinalAnswer(undefined)
    setPendingReview(undefined)
    setReviewDraft('')
  }

  async function sendQuestion() {
    const value = question.trim()
    if (!value || loading) return
    const userMessage: ChatMessage = { id: createMessageId(), role: 'user', content: value }
    const assistantMessage: ChatMessage = { id: createMessageId(), role: 'assistant', content: '' }
    const nextMessages = [...messages, userMessage, assistantMessage]

    setQuestion('')
    setLoading(true)
    setTraces([])
    setSources([])
    setSimilarTickets([])
    setFinalAnswer(undefined)
    setPendingReview(undefined)
    setReviewDraft('')
    setMessages(nextMessages)
    saveConversationSession({
      sessionId,
      messages: nextMessages,
      status: 'pending',
    })

    try {
      const res = await api.supportops.chat({ session_id: sessionId, message: value })
      const reader = res.data.getReader()
      if (reader) {
        const result = await readStream(reader)
        if (result.finalReceived && result.finalAnswer) {
          const reply = result.finalAnswer.reply || result.streamedReply
          const completedMessages = replaceMessageContent(nextMessages, assistantMessage.id, reply)
          setMessages(completedMessages)
          saveConversationSession({
            sessionId,
            messages: completedMessages,
            status: 'success',
            finalAnswer: result.finalAnswer,
            traces: result.finalAnswer.agent_trace || [],
            sources: result.finalAnswer.sources || [],
            similarTickets: result.finalAnswer.similar_tickets || [],
          })
        } else if (result.approval) {
          const reply = `【待人工审核】\n${result.approval.proposed_reply || '高风险问题已暂停，等待人工处理。'}`
          const pendingMessages = replaceMessageContent(nextMessages, assistantMessage.id, reply)
          setMessages(pendingMessages)
          saveConversationSession({
            sessionId,
            messages: pendingMessages,
            status: 'pending',
            traces: result.traces,
            sources: result.sources,
            similarTickets: result.similarTickets,
          })
        } else {
          const reply = result.streamedReply || '未收到最终结果'
          const failedMessages = replaceMessageContent(nextMessages, assistantMessage.id, reply)
          setMessages(failedMessages)
          saveConversationSession({
            sessionId,
            messages: failedMessages,
            status: 'failed',
          })
        }
      } else {
        const failedMessages = replaceMessageContent(nextMessages, assistantMessage.id, '无法读取流式响应')
        setMessages(failedMessages)
        saveConversationSession({
          sessionId,
          messages: failedMessages,
          status: 'failed',
        })
      }
    } catch (error) {
      const errorMessage = (error as Error)?.message || '请求失败'
      const failedMessages = replaceMessageContent(nextMessages, assistantMessage.id, errorMessage)
      setMessages(failedMessages)
      saveConversationSession({
        sessionId,
        messages: failedMessages,
        status: 'failed',
      })
    } finally {
      setLoading(false)
    }
  }

  async function submitHumanReview(action: 'approve' | 'edit' | 'reject') {
    if (!pendingReview || loading) return
    if (action === 'edit' && !reviewDraft.trim()) {
      antdMessage.warning('请填写人工修改后的回复')
      return
    }

    setLoading(true)
    const clearedMessages = messages.map((item, index) =>
      index === messages.length - 1 && item.role === 'assistant' ? { ...item, content: '' } : item,
    )
    setMessages(clearedMessages)
    try {
      const res = await api.supportops.resumeChat({
        session_id: sessionId,
        action,
        edited_reply: action === 'edit' ? reviewDraft.trim() : undefined,
      })
      const result = await readStream(res.data.getReader())
      if (!result.finalReceived || !result.finalAnswer) {
        throw new Error('人工审核后未收到最终结果')
      }
      const completedMessages = replaceMessageContent(
        clearedMessages,
        clearedMessages[clearedMessages.length - 1].id,
        result.finalAnswer.reply || result.streamedReply,
      )
      setMessages(completedMessages)
      setPendingReview(undefined)
      setReviewDraft('')
      saveConversationSession({
        sessionId,
        messages: completedMessages,
        status: 'success',
        finalAnswer: result.finalAnswer,
        traces: result.finalAnswer.agent_trace || [],
        sources: result.finalAnswer.sources || [],
        similarTickets: result.finalAnswer.similar_tickets || [],
      })
      antdMessage.success('人工审核已提交，工作流已恢复')
    } catch (error) {
      antdMessage.error((error as Error)?.message || '人工审核提交失败')
    } finally {
      setLoading(false)
    }
  }

  function logout() {
    userActions.setToken('')
    navigate('/login')
  }

  const riskPercent = Math.round((metrics?.high_risk_ratio || 0) * 100)
  const totalLatency = traces.reduce((total, item) => total + (item.latency_ms || 0), 0)
  const currentStatus = pendingReview ? '等待人工审核' : loading ? 'Agent 执行中' : '服务就绪'
  const persistenceStatus = !workflowStatus
    ? '同步中'
    : workflowStatus.durable
      ? '持久化'
      : '内存模式'
  const starterQuestions = [
    '支付失败但已经扣款，应该如何处理？',
    '用户要求退款并投诉服务体验',
    '产品批量导入功能无法使用',
  ]

  return (
    <div className="supportops-page">
      <header className="supportops-topbar">
        <div className="supportops-brand">
          <div className="supportops-brand__mark"><ApartmentOutlined /></div>
          <div>
            <div className="supportops-brand__name">SupportOps</div>
            <div className="supportops-brand__edition">AI SERVICE OPERATIONS</div>
          </div>
        </div>
        <div className="supportops-topbar__status">
          <span className="supportops-live-dot" />
          本地运营工作区
        </div>
        <Space className="supportops-page__account" size={12}>
          <div className="supportops-user">
            <span className="supportops-user__avatar"><UserOutlined /></span>
            <span>
              <strong>{user.username || 'Operator'}</strong>
              <small>客服运营人员</small>
            </span>
          </div>
          <Button
            className="supportops-logout"
            type="text"
            icon={<LogoutOutlined />}
            onClick={logout}
            aria-label="退出登录"
          >
            退出登录
          </Button>
        </Space>
      </header>

      <main className="supportops-workspace">
        <div className="supportops-page__header">
          <div>
            <div className="supportops-page__eyebrow">CUSTOMER SUPPORT CONTROL CENTER</div>
            <h1 className="supportops-page__title">智能客服运营工作台</h1>
            <div className="supportops-page__subtitle">统一处理客服问答、风险升级、知识检索与人工审核</div>
          </div>
          <div className="supportops-session-card">
            <span>当前会话</span>
            <strong>{sessionId}</strong>
          </div>
        </div>

        <div className="supportops-status-grid">
          <div className="supportops-status-card">
            <span className="supportops-status-card__icon is-green"><CloudServerOutlined /></span>
            <div><small>Agent Runtime</small><strong>{workflowStatus?.framework || 'LangGraph'}</strong></div>
            <span className="supportops-status-card__state"><CheckCircleFilled /> {persistenceStatus}</span>
          </div>
          <div className="supportops-status-card">
            <span className="supportops-status-card__icon is-blue"><DatabaseOutlined /></span>
            <div><small>知识与工单</small><strong>{ticketTotal.toLocaleString()}</strong></div>
            <span className="supportops-status-card__hint">已入库记录</span>
          </div>
          <div className="supportops-status-card">
            <span className="supportops-status-card__icon is-amber"><SafetyCertificateOutlined /></span>
            <div><small>高风险占比</small><strong>{riskPercent}%</strong></div>
            <span className="supportops-status-card__hint">自动升级策略</span>
          </div>
          <div className="supportops-status-card">
            <span className="supportops-status-card__icon is-violet"><ThunderboltOutlined /></span>
            <div><small>当前运行状态</small><strong>{currentStatus}</strong></div>
            <span className="supportops-status-card__hint">{traces.length ? `${traces.length} 节点 · ${totalLatency}ms` : '等待任务'}</span>
          </div>
        </div>

      <Tabs
        className="supportops-tabs"
        defaultActiveKey="agent"
        items={[
          {
            key: 'agent',
            label: (
              <span>
                <MessageOutlined /> Agent 工作台
              </span>
            ),
            children: (
              <div className="supportops-tab-grid supportops-tab-grid--agent">
                <div className="supportops-page__main">
                  <div className="supportops-section supportops-section--chat">
                    <div className="supportops-section__header">
                      <div>
                        <div className="supportops-section__kicker">LIVE CASE</div>
                        <div className="supportops-section__title">工单协同处理</div>
                        <div className="supportops-section__meta">Agent 自动检索证据、识别风险并生成可审核回复</div>
                      </div>
                      <Space className="supportops-section__actions" wrap>
                        <Button
                          icon={<CommentOutlined />}
                          onClick={() => window.open('/portal', '_blank')}
                          title="打开客户视角的工单提交窗口（新标签页）"
                        >
                          客户模拟窗口
                        </Button>
                        <Button
                          icon={<PlusOutlined />}
                          onClick={startNewConversation}
                          disabled={loading}
                        >
                          开启新对话
                        </Button>
                        {finalAnswer ? (
                          <>
                            <span className={`supportops-badge is-${finalAnswer.risk_level}`}>{finalAnswer.risk_level} risk</span>
                            <span className="supportops-badge is-action">{finalAnswer.next_action}</span>
                          </>
                        ) : null}
                      </Space>
                    </div>

                    <div className="supportops-chat">
                      <div className="supportops-chat__messages" aria-live="polite" aria-busy={loading}>
                        {messages.length === 0 ? (
                          <div className="supportops-chat-empty">
                            <div className="supportops-chat-empty__icon"><MessageOutlined /></div>
                            <strong>创建一个客服处理任务</strong>
                            <p>输入客户问题，系统将自动执行意图分类、知识检索、风险判断与回复生成。</p>
                            <div className="supportops-chat-empty__suggestions">
                              {starterQuestions.map((item) => (
                                <button type="button" key={item} onClick={() => setQuestion(item)}>{item}</button>
                              ))}
                            </div>
                          </div>
                        ) : (
                          messages.map((item) => (
                            <div key={item.id} className={`supportops-chat-row supportops-chat-row--${item.role}`}>
                              <span className="supportops-chat-row__avatar">
                                {item.role === 'assistant' ? <ApartmentOutlined /> : <UserOutlined />}
                              </span>
                              <div>
                                <small>{item.role === 'assistant' ? 'SupportOps Agent' : '客户问题'}</small>
                                <div className={`supportops-chat__message supportops-chat__message--${item.role}`}>
                                  {item.content || (item.role === 'assistant' && loading ? '正在分析并检索证据…' : '')}
                                </div>
                              </div>
                            </div>
                          ))
                        )}
                      </div>

                      <div className="supportops-chat__input">
                        <Input.TextArea
                          value={question}
                          onChange={(event) => setQuestion(event.target.value)}
                          placeholder="粘贴客户问题，或描述需要处理的服务场景…"
                          aria-label="客户问题"
                          autoSize={{ minRows: 2, maxRows: 5 }}
                          onPressEnter={(event) => {
                            if (!event.shiftKey) {
                              event.preventDefault()
                              sendQuestion()
                            }
                          }}
                        />
                        <Button
                          type="primary"
                          icon={<SendOutlined />}
                          loading={loading}
                          onClick={sendQuestion}
                          disabled={!question.trim()}
                        >
                          发送
                        </Button>
                      </div>
                      <div className="supportops-chat__footer">
                        <span><CheckCircleFilled /> PostgreSQL checkpoint enabled</span>
                        <span>Enter 发送 · Shift + Enter 换行</span>
                      </div>
                    </div>
                  </div>

                  {pendingReview ? (
                    <div className="supportops-section supportops-review">
                      <Alert
                        type="warning"
                        showIcon
                        message={`高风险工作流已暂停：${pendingReview.risk_level}`}
                        description={pendingReview.reason || '请人工检查回复后决定是否发送。'}
                      />
                      <Input.TextArea
                        value={reviewDraft}
                        onChange={(event) => setReviewDraft(event.target.value)}
                        autoSize={{ minRows: 4, maxRows: 10 }}
                        placeholder="检查或修改拟发送回复"
                      />
                      <Space wrap>
                        <Button type="primary" onClick={() => submitHumanReview('approve')} loading={loading}>
                          批准原回复
                        </Button>
                        <Button onClick={() => submitHumanReview('edit')} disabled={!reviewDraft.trim() || loading}>
                          修改后发送
                        </Button>
                        <Button danger onClick={() => submitHumanReview('reject')} disabled={loading}>
                          拒绝并转人工
                        </Button>
                      </Space>
                    </div>
                  ) : null}

                  {finalAnswer ? (
                    <div className="supportops-section">
                      <div className="supportops-section__header">
                        <div>
                          <div className="supportops-section__kicker">DECISION SUMMARY</div>
                          <div className="supportops-section__title">处理决策</div>
                        </div>
                        <span className="supportops-summary-evidence">{sources.length + similarTickets.length} 条证据 · {finalAnswer.retry_count || 0} 次重试</span>
                      </div>
                      <div className="supportops-final">
                        <div className="supportops-final__item">
                          <div className="supportops-final__label">问题分类</div>
                          <div className="supportops-final__value">{finalAnswer.category}</div>
                        </div>
                        <div className="supportops-final__item">
                          <div className="supportops-final__label">识别意图</div>
                          <div className="supportops-final__value">{finalAnswer.intent}</div>
                        </div>
                        <div className="supportops-final__item">
                          <div className="supportops-final__label">是否转人工</div>
                          <div className="supportops-final__value">
                            {finalAnswer.need_human ? '是' : '否'}
                          </div>
                        </div>
                        <div className="supportops-final__item">
                          <div className="supportops-final__label">下一步</div>
                          <div className="supportops-final__value">{finalAnswer.next_action}</div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="supportops-page__side">
                  <div className="supportops-section">
                    <div className="supportops-section__header">
                      <div>
                        <div className="supportops-section__kicker">CASE HISTORY</div>
                        <div className="supportops-section__title">会话记录</div>
                        <div className="supportops-section__meta">最近 {conversationHistory.length} 个处理会话</div>
                      </div>
                    </div>
                    <div className="supportops-question-history">
                      {conversationHistory.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      ) : (
                        conversationHistory.map((item, index) => (
                          <button
                            key={item.id}
                            className={`supportops-question-history__item${item.sessionId === sessionId ? ' is-active' : ''}`}
                            onClick={() => restoreConversation(item)}
                            type="button"
                            aria-current={item.sessionId === sessionId ? 'true' : undefined}
                          >
                            <span>{index + 1}</span>
                            <div className="supportops-question-history__content">
                              <strong>{item.title}</strong>
                              <em>
                                {item.latestReply ||
                                  item.latestQuestion ||
                                  (item.status === 'pending' ? '处理中...' : '暂无回复内容')}
                              </em>
                              <div className="supportops-question-history__tags">
                                <Tag>{item.turnCount} 轮</Tag>
                                {item.finalAnswer ? (
                                  <>
                                  <Tag color={item.finalAnswer.risk_level === 'high' ? 'red' : 'green'}>
                                    {item.finalAnswer.risk_level}
                                  </Tag>
                                  <Tag color={item.finalAnswer.need_human ? 'orange' : 'blue'}>
                                    {item.finalAnswer.next_action}
                                  </Tag>
                                  </>
                                ) : (
                                  <Tag color={item.status === 'failed' ? 'red' : 'gold'}>
                                    {item.status === 'pending' ? '处理中' : '失败'}
                                  </Tag>
                                )}
                              </div>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                  <AgentTrace traces={traces} />
                  <SourceList sources={sources} similarTickets={similarTickets} />
                </div>
              </div>
            ),
          },
          {
            key: 'ops',
            label: (
              <span>
                <DatabaseOutlined /> 运营与配置
              </span>
            ),
            children: (
              <div className="supportops-tab-grid supportops-tab-grid--ops">
                <div className="supportops-page__main">
                  <TicketPanel
                    tickets={tickets}
                    total={ticketTotal}
                    loading={ticketsLoading}
                    lastDocsUpload={lastDocsUpload}
                    onUploadTickets={handleUploadTickets}
                    onImportDataset={handleImportDataset}
                    onUploadDocs={handleUploadDocs}
                    onUpdateTicket={handleUpdateTicket}
                    onRefresh={refreshData}
                  />
                  <ApiKeyPanel />
                </div>

                <div className="supportops-page__side">
                  <MetricsPanel metrics={metrics} />
                </div>
              </div>
            ),
          },
        ]}
      />
      </main>
    </div>
  )
}
