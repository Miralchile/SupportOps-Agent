import { FileTextOutlined, HistoryOutlined } from '@ant-design/icons'
import { Empty, List, Tabs, Tag, Typography } from 'antd'

type Props = {
  sources: API.SupportSource[]
  similarTickets: API.SupportSimilarTicket[]
}

export default function SourceList(props: Props) {
  return (
    <div className="supportops-section">
      <div className="supportops-section__header">
        <div>
          <div className="supportops-section__kicker">GROUNDING</div>
          <div className="supportops-section__title">证据与引用</div>
          <div className="supportops-section__meta">回答依据可追溯，避免无依据生成</div>
        </div>
        <Tag>{props.sources.length + props.similarTickets.length} 条</Tag>
      </div>
      <Tabs
        size="small"
        items={[
          {
            key: 'docs',
            label: (
              <span>
                <FileTextOutlined /> 知识文档 ({props.sources.length})
              </span>
            ),
            children: props.sources.length ? (
              <List
                size="small"
                dataSource={props.sources}
                renderItem={(item) => (
                  <List.Item>
                    <div className="supportops-source-item">
                      <div className="supportops-source-item__title">
                        {item.document_name}
                        <Tag>{item.score.toFixed(2)}</Tag>
                      </div>
                      <Typography.Paragraph ellipsis={{ rows: 3 }}>
                        {item.content}
                      </Typography.Paragraph>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ),
          },
          {
            key: 'tickets',
            label: (
              <span>
                <HistoryOutlined /> 历史工单 ({props.similarTickets.length})
              </span>
            ),
            children: props.similarTickets.length ? (
              <List
                size="small"
                dataSource={props.similarTickets}
                renderItem={(item) => (
                  <List.Item>
                    <div className="supportops-source-item">
                      <div className="supportops-source-item__title">
                        #{item.id} {item.intent}
                        <Tag>{item.score.toFixed(2)}</Tag>
                      </div>
                      <Typography.Text strong>{item.instruction}</Typography.Text>
                      <Typography.Paragraph ellipsis={{ rows: 2 }}>
                        {item.response}
                      </Typography.Paragraph>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ),
          },
        ]}
      />
    </div>
  )
}
