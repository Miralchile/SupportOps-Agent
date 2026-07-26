import { DownloadOutlined, DownOutlined, EditOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Dropdown, Form, Input, List, Modal, Space, Table, Tag, Upload } from 'antd'
import { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useRef, useState } from 'react'

type Props = {
  tickets: API.SupportTicket[]
  total: number
  loading?: boolean
  lastDocsUpload?: API.SupportUploadDocsResult
  onUploadTickets: (file: File) => Promise<void>
  onImportDataset: (
    dataset: 'supportops_csv' | 'tweetsumm' | 'msdialog',
    file: File,
  ) => Promise<void>
  onImportBundled: (dataset: 'tweetsumm') => Promise<void>
  onUploadDocs: (files: File[]) => Promise<void>
  onUpdateTicket: (id: number, data: { instruction: string; response: string }) => Promise<void>
  onRefresh: () => void
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  user_provided: '自有',
  real_derived: '真实',
  real_anonymized: '真实',
  unknown: '未知',
}

const SPLIT_LABELS: Record<string, string> = {
  train: '训练',
  validation: '验证',
  test: '测试',
  unspecified: '未切分',
}

// 自有 CSV 走顶层"导入工单 CSV"按钮（带 embedding 索引），此处只列真正的外部数据集。
// TweetSumm 数据随仓库内置，点击确认后由后端直接导入；MSDialog 受官方授权限制需自备文件。
const DATASET_IMPORT_OPTIONS = [
  { key: 'tweetsumm', label: 'TweetSumm · 真实 · 一键导入', bundled: true, accept: '', title: '真实 Twitter 客服对话的人工摘要（real_derived），数据随仓库内置，确认后直接导入' },
  { key: 'msdialog', label: 'MSDialog · 真实 · 需自备文件', bundled: false, accept: '.json', title: '真实匿名技术支持对话（real_anonymized），官方要求申请访问，请自备 JSON 文件' },
] as const

export default function TicketPanel(props: Props) {
  const [editingTicket, setEditingTicket] = useState<API.SupportTicket>()
  const [saving, setSaving] = useState(false)
  const [editForm] = Form.useForm()
  const datasetInputRef = useRef<HTMLInputElement>(null)
  const pendingDatasetRef = useRef<(typeof DATASET_IMPORT_OPTIONS)[number]>()

  function handleDatasetMenuClick(key: string) {
    const option = DATASET_IMPORT_OPTIONS.find((item) => item.key === key)
    if (!option) return
    if (option.bundled) {
      Modal.confirm({
        title: '导入内置 TweetSumm 数据集',
        content: '将导入仓库内置的 train/validation/test 三个文件，约 1093 条真实客服对话摘要。重复导入会被校验和与内容哈希去重，不会产生重复数据。',
        okText: '确认导入',
        cancelText: '取消',
        onOk: () => props.onImportBundled('tweetsumm'),
      })
      return
    }
    const input = datasetInputRef.current
    if (!input) return
    pendingDatasetRef.current = option
    input.accept = option.accept
    input.value = ''
    input.click()
  }

  function openEdit(row: API.SupportTicket) {
    setEditingTicket(row)
    editForm.setFieldsValue({ instruction: row.instruction, response: row.response })
  }

  async function handleSaveEdit() {
    if (!editingTicket) return
    const values = await editForm.validateFields()
    setSaving(true)
    try {
      await props.onUpdateTicket(editingTicket.id, values)
      setEditingTicket(undefined)
    } finally {
      setSaving(false)
    }
  }

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
        const color = raw.startsWith('real') ? 'green' : raw === 'user_provided' ? 'blue' : undefined
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

      <Space wrap size={12} className="supportops-toolbar">
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

          <Dropdown
            trigger={['click']}
            menu={{
              items: DATASET_IMPORT_OPTIONS.map((option) => ({
                key: option.key,
                label: <span title={option.title}>{option.label}</span>,
              })),
              onClick: ({ key }) => handleDatasetMenuClick(key),
            }}
          >
            <Button icon={<DownloadOutlined />}>
              导入外部数据集
              <DownOutlined style={{ fontSize: 10 }} />
            </Button>
          </Dropdown>

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

      <input
        ref={datasetInputRef}
        type="file"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0]
          const option = pendingDatasetRef.current
          if (file && option) props.onImportDataset(option.key, file)
          event.target.value = ''
        }}
      />

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
        scroll={{ y: 300 }}
        expandable={{
          rowExpandable: (row) => Boolean(row.response),
          expandedRowRender: (row) => (
            <div className="supportops-ticket-answer">
              <div className="supportops-ticket-answer__label">
                处理方式 / 回答
                <Button
                  size="small"
                  type="link"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(row)}
                >
                  编辑
                </Button>
              </div>
              {row.response}
            </div>
          ),
        }}
      />

      <Modal
        title={`编辑工单 #${editingTicket?.id ?? ''}`}
        open={Boolean(editingTicket)}
        confirmLoading={saving}
        onOk={handleSaveEdit}
        onCancel={() => setEditingTicket(undefined)}
        destroyOnClose
        width={640}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="instruction"
            label="问题"
            rules={[{ required: true, whitespace: true, message: '请输入问题' }]}
          >
            <Input.TextArea rows={3} maxLength={8000} showCount />
          </Form.Item>
          <Form.Item
            name="response"
            label="处理方式 / 回答"
            rules={[{ required: true, whitespace: true, message: '请输入处理方式' }]}
            extra="保存后会走导入侧同样的清洗与脱敏，并同步重建该工单的检索索引与 embedding"
          >
            <Input.TextArea rows={6} maxLength={16000} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
