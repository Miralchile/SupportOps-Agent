import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { Empty, List, Tag, Typography } from 'antd'

function preview(value: API.SupportTrace['tool_output']) {
  if (!value) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 220 ? `${text.slice(0, 220)}...` : text
}

function llmCalls(trace: API.SupportTrace): NonNullable<API.SupportTrace['llm_calls']> {
  if (trace.llm_calls?.length) return trace.llm_calls
  if (trace.tool_output && typeof trace.tool_output === 'object') {
    const embedded = trace.tool_output._llm_calls
    return Array.isArray(embedded) ? embedded as NonNullable<API.SupportTrace['llm_calls']> : []
  }
  if (typeof trace.tool_output === 'string') {
    try {
      const parsed = JSON.parse(trace.tool_output)
      return Array.isArray(parsed?._llm_calls) ? parsed._llm_calls : []
    } catch {
      return []
    }
  }
  return []
}

export default function AgentTrace(props: { traces: API.SupportTrace[] }) {
  const succeeded = props.traces.filter((item) => item.status === 'success').length
  const totalLatency = props.traces.reduce((total, item) => total + (item.latency_ms || 0), 0)

  return (
    <div className="supportops-section">
      <div className="supportops-section__header">
        <div>
          <div className="supportops-section__kicker">OBSERVABILITY</div>
          <div className="supportops-section__title">Agent 执行轨迹</div>
          <div className="supportops-section__meta">节点输入输出、状态与耗时审计</div>
        </div>
        {props.traces.length ? <Tag color="blue">{succeeded}/{props.traces.length} · {totalLatency}ms</Tag> : null}
      </div>
      {props.traces.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="supportops-trace-scroll">
          <List
            size="small"
            dataSource={props.traces}
            renderItem={(item) => {
              const calls = llmCalls(item)
              return <List.Item>
                <div className="supportops-trace-item">
                  <div className="supportops-trace-item__head">
                    <span className="supportops-trace-item__name">
                      {item.status === 'success' ? (
                        <CheckCircleOutlined />
                      ) : item.status === 'failed' ? (
                        <CloseCircleOutlined />
                      ) : (
                        <ClockCircleOutlined />
                      )}
                      {String(item.step_order).padStart(2, '0')} · {item.tool_name}
                    </span>
                    <Tag color={item.status === 'success' ? 'green' : item.status === 'failed' ? 'red' : 'gold'}>
                      {item.status}
                    </Tag>
                    <span className="supportops-trace-item__latency">
                      {item.latency_ms}ms
                    </span>
                  </div>
                  {calls.map((call, index) => (
                    <div key={`${call.prompt_version}-${index}`}>
                      <Tag color={call.fallback_used ? 'orange' : 'blue'}>{call.model}</Tag>
                      <Tag>{call.prompt_version}</Tag>
                      <Tag>{call.input_tokens + call.output_tokens} tokens</Tag>
                      {call.fallback_used ? <Tag color="orange">fallback: {call.fallback_reason}</Tag> : null}
                    </div>
                  ))}
                  <Typography.Text type="secondary">{preview(item.tool_output)}</Typography.Text>
                </div>
              </List.Item>
            }}
          />
        </div>
      )}
    </div>
  )
}
