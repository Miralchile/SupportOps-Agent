import { InboxOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
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

export default function TicketPanel(props: Props) {
  const [datasetType, setDatasetType] = useState<'supportops_csv' | 'bitext' | 'tweetsumm' | 'msdialog'>('tweetsumm')
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
      dataIndex: 'source_type',
      width: 150,
      render(value: API.SupportTicket['source_type'], row) {
        const color = value === 'real_anonymized' ? 'green' : value === 'synthetic' ? 'purple' : 'blue'
        return <Tag color={color}>{value || row.source}</Tag>
      },
    },
    {
      title: '数据切分',
      dataIndex: 'dataset_split',
      width: 100,
      render(value: string) {
        return <Tag>{value}</Tag>
      },
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

          <Select
            value={datasetType}
            onChange={setDatasetType}
            style={{ width: 150 }}
            options={[
              { value: 'tweetsumm', label: 'TweetSumm · 真实衍生' },
              { value: 'msdialog', label: 'MSDialog · 真实匿名' },
              { value: 'bitext', label: 'Bitext · 合成' },
              { value: 'supportops_csv', label: '标准 CSV · 自有' },
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
            <Button icon={<UploadOutlined />}>导入外部数据集</Button>
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
        scroll={{ x: 900, y: 260 }}
      />
    </div>
  )
}
