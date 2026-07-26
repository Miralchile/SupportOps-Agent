import * as api from '@/api'
import {
  CheckCircleFilled,
  CustomerServiceOutlined,
  DesktopOutlined,
  LoadingOutlined,
  PlusOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { userState } from '@/store/user'
import { Button, Input, Tag, message as antdMessage } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useSnapshot } from 'valtio'
import './index.module.scss'

type PortalMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

type TurnStatus = 'idle' | 'running' | 'awaiting_review' | 'done'

function createSessionId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`.slice(0, 16)
}

function createMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// 与工作台 (pages/supportops) 共用同一份 localStorage 会话记录，
// 客户在本页提交的工单会实时出现在客服工作台的「会话记录」里。
const CONVERSATION_HISTORY_LIMIT = 50

function conversationHistoryStorageKey(username?: string | null) {
  return `supportops.conversation_history.${username || 'anonymous'}`
}

function upsertSharedHistory(
  username: string | null | undefined,
  entry: {
    sessionId: string
    messages: PortalMessage[]
    status: 'pending' | 'success' | 'failed'
    finalAnswer?: API.SupportFinalAnswer
  },
) {
  try {
    const key = conversationHistoryStorageKey(username)
    const list = JSON.parse(window.localStorage.getItem(key) || '[]')
    const items = Array.isArray(list) ? list : []
    const chatMessages = entry.messages
      .filter((item) => item.role !== 'system')
      .map((item) => ({ id: item.id, role: item.role, content: item.content }))
    const firstQuestion = chatMessages.find((item) => item.role === 'user')?.content || '客户工单'
    const now = new Date().toISOString()
    const existing = items.find((item: any) => item?.sessionId === entry.sessionId)
    const nextItem = {
      ...(existing || {}),
      id: entry.sessionId,
      sessionId: entry.sessionId,
      title: `[客户工单] ${firstQuestion}`.slice(0, 60),
      messages: chatMessages,
      latestQuestion: [...chatMessages].reverse().find((item) => item.role === 'user')?.content || firstQuestion,
      latestReply: [...chatMessages].reverse().find((item) => item.role === 'assistant')?.content || '',
      finalAnswer: entry.finalAnswer ?? existing?.finalAnswer,
      status: entry.status,
      createdAt: existing?.createdAt || now,
      updatedAt: now,
    }
    const next = [nextItem, ...items.filter((item: any) => item?.sessionId !== entry.sessionId)]
    window.localStorage.setItem(key, JSON.stringify(next.slice(0, CONVERSATION_HISTORY_LIMIT)))
  } catch {
    // localStorage 不可用时静默降级：仅影响工作台联动，不影响本页
  }
}

function parseSseLine(line: string) {
  const data = line.trim().replace(/^data: /, '').trim()
  if (!data || data === '[DONE]') return null
  return JSON.parse(data)
}

const STARTERS = [
  '订单 ORD123456 的物流到哪了？',
  '我要投诉，订单 ORD888777 扣了款却不发货，必须马上退款',
  '你们的退款政策是什么？',
]

export default function CustomerPortalPage() {
  const user = useSnapshot(userState)
  const [sessionId, setSessionId] = useState(createSessionId)
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState<TurnStatus>('idle')
  const [messages, setMessages] = useState<PortalMessage[]>([])
  const [ticketMeta, setTicketMeta] = useState<{ category?: string; next_action?: string }>()
  const messagesRef = useRef<HTMLDivElement>(null)
  const pollTimer = useRef<number>()

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, status])

  useEffect(() => () => window.clearInterval(pollTimer.current), [])

  function patchMessage(id: string, content: string) {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, content } : item)))
  }

  function startNewTicket() {
    if (status === 'running') return
    window.clearInterval(pollTimer.current)
    setSessionId(createSessionId())
    setMessages([])
    setTicketMeta(undefined)
    setStatus('idle')
    setDraft('')
  }

  /** 人工审核完成后，轮询后端消息记录取回客服的最终答复。 */
  function startReviewPolling(currentMessages: PortalMessage[], question: string) {
    let ticks = 0
    window.clearInterval(pollTimer.current)
    pollTimer.current = window.setInterval(async () => {
      ticks += 1
      if (ticks > 60) {
        window.clearInterval(pollTimer.current)
        return
      }
      try {
        const { data: review } = await api.supportops.pendingReview(sessionId, { loading: false })
        if (review.pending) return
        const { data } = await api.supportops.sessionMessages(sessionId, { loading: false })
        const answer = [...data.messages].reverse().find((item) => item.user_question === question)
        if (!answer) return
        window.clearInterval(pollTimer.current)
        const replyId = createMessageId()
        const finalMessages: PortalMessage[] = [
          ...currentMessages,
          { id: replyId, role: 'assistant', content: answer.model_answer },
          { id: createMessageId(), role: 'system', content: '人工客服已审核并回复' },
        ]
        setMessages(finalMessages)
        setStatus('done')
        upsertSharedHistory(user.username, { sessionId, messages: finalMessages, status: 'success' })
      } catch {
        // 单次轮询失败可忽略，下一轮继续
      }
    }, 4000)
  }

  async function submitTicket() {
    const question = draft.trim()
    if (!question || status === 'running') return

    const userMessage: PortalMessage = { id: createMessageId(), role: 'user', content: question }
    const assistantId = createMessageId()
    const baseMessages: PortalMessage[] = [...messages, userMessage]

    setDraft('')
    setStatus('running')
    setTicketMeta(undefined)
    setMessages([...baseMessages, { id: assistantId, role: 'assistant', content: '' }])
    upsertSharedHistory(user.username, { sessionId, messages: baseMessages, status: 'pending' })

    let streamedReply = ''
    let finalAnswer: API.SupportFinalAnswer | undefined
    let approval: API.SupportHumanReview | undefined

    try {
      const res = await api.supportops.chat({ session_id: sessionId, message: question })
      const reader = res.data.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value)
        while (true) {
          const index = buffer.indexOf('\n')
          if (index === -1) break
          const line = buffer.slice(0, index)
          buffer = buffer.slice(index + 1)
          if (!line.startsWith('data: ')) continue
          try {
            const payload = parseSseLine(line)
            if (payload?.type === 'reply_delta') {
              streamedReply += payload.content || ''
              patchMessage(assistantId, streamedReply)
            }
            if (payload?.type === 'final') finalAnswer = payload.final
            if (payload?.type === 'human_approval_required') approval = payload.approval
          } catch {
            // 忽略无法解析的行
          }
        }
        if (done) break
      }

      if (finalAnswer) {
        const reply = finalAnswer.reply || streamedReply || '已收到您的问题，我们会尽快处理。'
        const doneMessages: PortalMessage[] = [...baseMessages, { id: assistantId, role: 'assistant', content: reply }]
        setMessages(doneMessages)
        setTicketMeta({ category: finalAnswer.category, next_action: finalAnswer.next_action })
        setStatus('done')
        upsertSharedHistory(user.username, {
          sessionId,
          messages: doneMessages,
          status: 'success',
          finalAnswer,
        })
        return
      }

      if (approval) {
        const waitingMessages: PortalMessage[] = [
          ...baseMessages,
          {
            id: assistantId,
            role: 'system',
            content: '您的问题涉及需要人工确认的场景，已生成工单并转交人工客服审核，请稍候…',
          },
        ]
        setMessages(waitingMessages)
        setStatus('awaiting_review')
        upsertSharedHistory(user.username, { sessionId, messages: baseMessages, status: 'pending' })
        startReviewPolling(baseMessages, question)
        return
      }

      throw new Error('未收到处理结果')
    } catch (error) {
      const failedMessages: PortalMessage[] = [
        ...baseMessages,
        { id: assistantId, role: 'system', content: (error as Error)?.message || '提交失败，请稍后重试' },
      ]
      setMessages(failedMessages)
      setStatus('idle')
      upsertSharedHistory(user.username, { sessionId, messages: failedMessages, status: 'failed' })
      antdMessage.error('提交失败，请稍后重试')
    }
  }

  const statusHint =
    status === 'running'
      ? { icon: <LoadingOutlined spin />, text: '客服助手正在处理您的问题…' }
      : status === 'awaiting_review'
        ? { icon: <LoadingOutlined spin />, text: '等待人工客服审核，页面会自动刷新结果' }
        : status === 'done'
          ? { icon: <CheckCircleFilled />, text: '本次咨询已完成，可继续追问或发起新工单' }
          : undefined

  return (
    <div className="portal-page">
      <main className="portal-card">
        <header className="portal-card__header">
          <span className="portal-card__logo">
            <CustomerServiceOutlined />
          </span>
          <div className="portal-card__title">
            <strong>SupportOps 客户服务中心</strong>
            <small>
              <span className="portal-live-dot" /> 在线 · 通常在几秒内响应
            </small>
          </div>
          <div className="portal-card__meta">
            <Tag color="blue">演示模式 · 客户视角</Tag>
            <Button size="small" type="text" icon={<PlusOutlined />} onClick={startNewTicket} disabled={status === 'running'}>
              新工单
            </Button>
            <Button
              size="small"
              type="text"
              icon={<DesktopOutlined />}
              onClick={() => window.open('/supportops', '_blank')}
              title="切换到客服工作台视角（新标签页）"
            >
              客服工作台
            </Button>
          </div>
        </header>

        <div className="portal-messages" ref={messagesRef} aria-live="polite">
          {messages.length === 0 ? (
            <div className="portal-empty">
              <strong>您好，请描述遇到的问题</strong>
              <p>系统会自动检索知识库并查询订单 / 物流 / 退款状态；涉及资金或投诉的问题将转交人工客服审核后回复。</p>
              <div className="portal-empty__starters">
                {STARTERS.map((item) => (
                  <button key={item} type="button" onClick={() => setDraft(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((item) =>
              item.role === 'system' ? (
                <div key={item.id} className="portal-system-note">
                  {item.content}
                </div>
              ) : (
                <div key={item.id} className={`portal-row portal-row--${item.role}`}>
                  <span className="portal-row__avatar">
                    {item.role === 'assistant' ? <CustomerServiceOutlined /> : <UserOutlined />}
                  </span>
                  <div className={`portal-bubble portal-bubble--${item.role}`}>
                    {item.content || (status === 'running' ? '正在输入…' : '')}
                  </div>
                </div>
              ),
            )
          )}
        </div>

        {statusHint || ticketMeta ? (
          <div className="portal-statusbar">
            {statusHint ? (
              <span className="portal-statusbar__hint">
                {statusHint.icon} {statusHint.text}
              </span>
            ) : null}
            {ticketMeta ? (
              <span className="portal-statusbar__tags">
                {ticketMeta.category ? <Tag>{ticketMeta.category}</Tag> : null}
                {ticketMeta.next_action ? <Tag color="blue">{ticketMeta.next_action}</Tag> : null}
              </span>
            ) : null}
          </div>
        ) : null}

        <footer className="portal-input">
          <Input.TextArea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="请输入您的问题，例如：订单 ORD123456 的物流到哪了？"
            autoSize={{ minRows: 2, maxRows: 5 }}
            aria-label="问题描述"
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault()
                submitTicket()
              }
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={status === 'running'}
            disabled={!draft.trim()}
            onClick={submitTicket}
          >
            提交
          </Button>
        </footer>
        <div className="portal-foot">工单编号 {sessionId} · 由 SupportOps Agent 提供支持 · 客服工作台可实时看到本会话</div>
      </main>
    </div>
  )
}
