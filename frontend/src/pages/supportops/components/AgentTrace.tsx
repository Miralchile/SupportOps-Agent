import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { Empty, List, Tag, Typography } from 'antd'

function preview(value: API.SupportTrace['tool_output']) {
  if (!value) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 220 ? `${text.slice(0, 220)}...` : text
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
            renderItem={(item) => (
              <List.Item>
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
                    <Tag color={item.status === 'success' ? 'green' : 'red'}>{item.status}</Tag>
                    <span className="supportops-trace-item__latency">
                      {item.latency_ms}ms
                    </span>
                  </div>
                  <Typography.Text type="secondary">{preview(item.tool_output)}</Typography.Text>
                </div>
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  )
}
