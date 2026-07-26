import { DownloadOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, List, Select, Space, Table, Tag, Upload } from 'antd'
import { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useState } from 'react'

type Props = {
  tickets: API.SupportTicket[]
  total: number
  loading?: boolean
  lastDocsUpload?: API.SupportUploadDocsResult
  importJobs: API.SupportDatasetImportJob[]
  onUploadTickets: (file: File) => Promise<void>
  onImportDataset: (
    dataset: 'supportops_csv' | 'bitext' | 'tweetsumm' | 'msdialog',
    file: File,
  ) => Promise<void>
  onUploadDocs: (files: File[]) => Promise<void>
  onRefresh: () => void
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  user_provided: '自有',
  real_derived: '真实',
  real_anonymized: '真实',
  synthetic: '合成',
  unknown: '未知',
}

const SPLIT_LABELS: Record<string, string> = {
  train: '训练',
  validation: '验证',
  test: '测试',
  unspecified: '未切分',
}

export default function TicketPanel(props: Props) {
  const [datasetType, setDatasetType] = useState<'supportops_csv' | 'bitext' | 'tweetsumm' | 'msdialog'>('supportops_csv')
  const columns: ColumnsType<API.SupportTicket> = [
    {
      title: '问题',
      dataIndex: 'instruction',
      ellipsis: true,
    },
    {
      title: '分类 / 意图',
      dataIndex: 'category',
      width: 200,
      ellipsis: true,
      render(_: string, row) {
        return (
          <>
            <Tag style={{ marginRight: 6 }}>{row.category}</Tag>
            <span className="supportops-table-sub" title={row.intent}>{row.intent}</span>
          </>
        )
      },
    },
    {
      title: '来源 · 切分',
      dataIndex: 'source_type',
      width: 176,
      ellipsis: true,
      render(value: API.SupportTicket['source_type'], row) {
        const raw = value || row.source
        const color = raw.startsWith('real') ? 'green' : raw === 'synthetic' ? 'purple' : raw === 'user_provided' ? 'blue' : undefined
        return (
          <>
            <Tag style={{ marginRight: 4 }} color={color} title={raw}>{SOURCE_TYPE_LABELS[raw] || raw}</Tag>
            <Tag style={{ margin: 0 }} title={row.dataset_split}>{SPLIT_LABELS[row.dataset_split] || row.dataset_split}</Tag>
          </>
        )
      },
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 92,
      render(value: string) {
        return <span className="supportops-table-sub">{dayjs(value).format('MM-DD HH:mm')}</span>
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
      </div>

      <Space wrap className="supportops-toolbar">
          <Upload
            accept=".csv"
            showUploadList={false}
            beforeUpload={(file) => {
              props.onUploadTickets(file)
              return false
            }}
          >
            <Button icon={<DownloadOutlined />} type="primary">
              导入工单 CSV
            </Button>
          </Upload>

          <Select
            value={datasetType}
            onChange={setDatasetType}
            style={{ width: 150 }}
            popupMatchSelectWidth={false}
            options={[
              { value: 'supportops_csv', label: 'CSV · 自有', title: '来源：用户自有数据（user_provided）' },
              { value: 'tweetsumm', label: 'TweetSumm · 真实', title: '来源：真实 Twitter 客服对话的人工摘要（real_derived）' },
              { value: 'msdialog', label: 'MSDialog · 真实', title: '来源：真实匿名技术支持对话（real_anonymized，需官方授权获取）' },
              { value: 'bitext', label: 'Bitext · 合成', title: '来源：机器合成客服数据（synthetic）' },
            ]}
          />
          <Upload
            accept={datasetType === 'msdialog' ? '.json' : datasetType === 'tweetsumm' ? '.jsonl' : '.csv'}
            showUploadList={false}
            beforeUpload={(file) => {
              props.onImportDataset(datasetType, file)
              return false
            }}
          >
            <Button icon={<DownloadOutlined />}>导入外部数据集</Button>
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

          <Button
            icon={<ReloadOutlined />}
            onClick={props.onRefresh}
            aria-label="刷新工单数据"
            title="刷新工单数据"
          />
      </Space>

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

      {props.importJobs[0] ? (
        <Alert
          className="supportops-upload-status"
          type={props.importJobs[0].status === 'success' ? 'success' : 'warning'}
          showIcon
          message={
            <Space wrap>
              <strong>最近数据批次 #{props.importJobs[0].id}</strong>
              <Tag color={props.importJobs[0].source_type === 'real_anonymized' ? 'green' : 'purple'}>
                {props.importJobs[0].dataset_name} · {props.importJobs[0].source_type}
              </Tag>
              <span>接收 {props.importJobs[0].accepted_rows}</span>
              <span>去重 {props.importJobs[0].duplicate_rows}</span>
              <span>脱敏 {props.importJobs[0].pii_redacted_rows}</span>
              <span>索引 {props.importJobs[0].indexed_rows}</span>
            </Space>
          }
          description={`train ${props.importJobs[0].split_counts.train || 0} · validation ${props.importJobs[0].split_counts.validation || 0} · test ${props.importJobs[0].split_counts.test || 0}`}
        />
      ) : null}

      <Table<API.SupportTicket>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={props.tickets}
        loading={props.loading}
        pagination={false}
        scroll={{ y: 300 }}
        expandable={{
          rowExpandable: (row) => Boolean(row.response),
          expandedRowRender: (row) => (
            <div className="supportops-ticket-answer">
              <div className="supportops-ticket-answer__label">处理方式 / 回答</div>
              {row.response}
            </div>
          ),
        }}
      />
    </div>
  )
}
