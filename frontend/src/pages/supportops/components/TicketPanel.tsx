import { InboxOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, Button, List, Space, Table, Tag, Upload } from 'antd'
import { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

type Props = {
  tickets: API.SupportTicket[]
  total: number
  loading?: boolean
  lastDocsUpload?: API.SupportUploadDocsResult
  onUploadTickets: (file: File) => Promise<void>
  onUploadDocs: (files: File[]) => Promise<void>
  onRefresh: () => void
}

export default function TicketPanel(props: Props) {
  const columns: ColumnsType<API.SupportTicket> = [
    {
      title: '问题',
      dataIndex: 'instruction',
      ellipsis: true,
    },
    {
      title: 'Category',
      dataIndex: 'category',
      width: 130,
    },
    {
      title: 'Intent',
      dataIndex: 'intent',
      width: 150,
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 130,
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 150,
      render(value: string) {
        return dayjs(value).format('MM-DD HH:mm')
      },
    },
  ]

  return (
    <div className="supportops-section">
      <div className="supportops-section__header">
        <div>
          <div className="supportops-section__kicker">KNOWLEDGE OPERATIONS</div>
          <div className="supportops-section__title">知识与工单资产</div>
          <div className="supportops-section__meta">维护历史服务记录与 FAQ 检索语料 · 共 {props.total} 条工单</div>
        </div>
        <Space>
          <Upload
            accept=".csv"
            showUploadList={false}
            beforeUpload={(file) => {
              props.onUploadTickets(file)
              return false
            }}
          >
            <Button icon={<UploadOutlined />} type="primary">
              导入工单 CSV
            </Button>
          </Upload>

          <Upload
            multiple
            accept=".pdf,.doc,.docx,.txt,.md,.markdown"
            showUploadList={false}
            beforeUpload={(file) => {
              props.onUploadDocs([file])
              return false
            }}
          >
            <Button icon={<InboxOutlined />}>导入知识文档</Button>
          </Upload>

          <Button icon={<ReloadOutlined />} onClick={props.onRefresh} />
        </Space>
      </div>

      {props.lastDocsUpload ? (
        <Alert
          className="supportops-upload-status"
          type={props.lastDocsUpload.status === 'success' ? 'success' : 'warning'}
          showIcon
          message={
            <Space wrap>
              <span>{props.lastDocsUpload.message}</span>
              <Tag>{props.lastDocsUpload.index_name}</Tag>
              <Tag color={props.lastDocsUpload.indexed_chunks > 0 ? 'blue' : 'orange'}>
                本次 {props.lastDocsUpload.indexed_chunks} 片段
              </Tag>
              <Tag>累计 {props.lastDocsUpload.total_chunks} 片段</Tag>
            </Space>
          }
          description={
            props.lastDocsUpload.file_results?.length ? (
              <List
                size="small"
                dataSource={props.lastDocsUpload.file_results}
                renderItem={(item) => (
                  <List.Item>
                    <Space wrap>
                      <span>{item.file_name}</span>
                      <Tag color={item.indexed > 0 ? 'green' : 'red'}>{item.status}</Tag>
                      <span>parsed {item.parsed}</span>
                      <span>indexed {item.indexed}</span>
                      {item.errors?.length ? <span>{item.errors[0]}</span> : null}
                    </Space>
                  </List.Item>
                )}
              />
            ) : null
          }
        />
      ) : null}

      <Table<API.SupportTicket>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={props.tickets}
        loading={props.loading}
        pagination={false}
        scroll={{ x: 760, y: 260 }}
      />
    </div>
  )
}
