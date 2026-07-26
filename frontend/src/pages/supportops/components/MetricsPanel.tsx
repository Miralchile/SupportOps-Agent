import { Progress, Statistic, Tag } from 'antd'

function distributionItems(data: Record<string, number>) {
  return Object.entries(data)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
}

export default function MetricsPanel(props: { metrics?: API.SupportMetrics }) {
  const metrics = props.metrics
  const highRiskPercent = Math.round((metrics?.high_risk_ratio || 0) * 100)
  const humanPercent = Math.round((metrics?.human_transfer_ratio || 0) * 100)

  return (
    <div className="supportops-section">
      <div className="supportops-section__header">
        <div>
          <div className="supportops-section__kicker">OPERATIONS</div>
          <div className="supportops-section__title">运营指标</div>
          <div className="supportops-section__meta">基于已处理工单与升级轨迹统计</div>
        </div>
      </div>
      <div className="supportops-metrics">
        <Statistic title="已入库工单" value={metrics?.ticket_total || 0} />
        <div>
          <div className="supportops-metrics__label">高风险比例</div>
          <Progress percent={highRiskPercent} size="small" strokeColor="#d92d20" />
        </div>
        <div>
          <div className="supportops-metrics__label">转人工比例</div>
          <Progress percent={humanPercent} size="small" strokeColor="#3157d5" />
        </div>
      </div>

      <div className="supportops-distribution">
        <div>
          <div className="supportops-distribution__title">问题分类分布</div>
          {distributionItems(metrics?.category_distribution || {}).map(([key, value]) => (
            <Tag key={key}>
              {key} {value}
            </Tag>
          ))}
        </div>
        <div>
          <div className="supportops-distribution__title">高频意图 Top 10</div>
          {(metrics?.top_intents || []).map((item) => (
            <Tag key={item.intent}>
              {item.intent} {item.count}
            </Tag>
          ))}
        </div>
        <div>
          <div className="supportops-distribution__title">风险等级分布</div>
          {distributionItems(metrics?.risk_level_distribution || {}).map(([key, value]) => (
            <Tag key={key}>
              {key} {value}
            </Tag>
          ))}
        </div>
      </div>
    </div>
  )
}
