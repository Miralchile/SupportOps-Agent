import * as api from '@/api'
import { CheckCircleOutlined, DeleteOutlined, EditOutlined, ExperimentOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, Modal, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd'
import { useEffect, useState } from 'react'

const DEFAULT_VALUES = {
  name: 'DashScope',
  provider: 'dashscope',
  base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  model: 'qwen-plus',
  embedding_model: 'text-embedding-v3',
  is_active: true,
}

export default function ApiKeyPanel() {
  const [form] = Form.useForm()
  const [keys, setKeys] = useState<API.SupportApiKey[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [testingCurrent, setTestingCurrent] = useState(false)
  const [testingId, setTestingId] = useState<number>()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<API.SupportApiKey>()

  async function loadKeys() {
    setLoading(true)
    try {
      const { data } = await api.supportops.apiKeys({ loading: false })
      setKeys(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadKeys()
  }, [])

  function openCreateModal() {
    setEditing(undefined)
    form.setFieldsValue(DEFAULT_VALUES)
    setModalOpen(true)
  }

  function openEditModal(record: API.SupportApiKey) {
    setEditing(record)
    form.setFieldsValue({
      name: record.name,
      provider: 'dashscope',
      api_key: '',
      base_url: record.base_url,
      model: record.model,
      embedding_model: record.embedding_model,
      is_active: record.is_active,
    })
    setModalOpen(true)
  }

  function showTestResult(result: API.SupportApiKeyTestResult) {
    if (result.chat_ok && result.embedding_ok) {
      message.success(result.message)
      return
    }
    message.error(result.message)
  }

  async function handleTestCurrentConfig() {
    const values = await form.validateFields()
    const hasNewApiKey = Boolean(values.api_key)
    if (editing && !hasNewApiKey) {
      await handleTestSaved(editing)
      return
    }

    setTestingCurrent(true)
    try {
      const { data } = await api.supportops.testApiKey({
        provider: 'dashscope',
        api_key: values.api_key,
        base_url: values.base_url,
        model: values.model,
        embedding_model: values.embedding_model,
      }, { loading: false })
      showTestResult(data)
    } finally {
      setTestingCurrent(false)
    }
  }

  async function handleSubmit() {
    const values = await form.validateFields()
    const payload: API.SupportApiKeyPayload = {
      name: values.name,
      provider: 'dashscope',
      api_key: values.api_key,
      base_url: values.base_url,
      model: values.model,
      embedding_model: values.embedding_model,
      is_active: values.is_active ?? true,
    }
    if (editing && !payload.api_key) {
      delete payload.api_key
    }

    setSubmitting(true)
    try {
      if (editing) {
        await api.supportops.updateApiKey(editing.id, payload)
        message.success('API Key 已更新')
      } else {
        await api.supportops.createApiKey(payload)
        message.success('API Key 已新增')
      }
      setModalOpen(false)
      loadKeys()
    } finally {
      setSubmitting(false)
    }
  }

  async function handleActivate(record: API.SupportApiKey) {
    await api.supportops.activateApiKey(record.id)
    message.success('已设为启用')
    loadKeys()
  }

  async function handleTestSaved(record: API.SupportApiKey) {
    setTestingId(record.id)
    try {
      const { data } = await api.supportops.testSavedApiKey(record.id, { loading: false })
      showTestResult(data)
    } finally {
      setTestingId(undefined)
    }
  }

  async function handleDelete(record: API.SupportApiKey) {
    await api.supportops.deleteApiKey(record.id)
    message.success('API Key 已删除')
    loadKeys()
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (value: string, record: API.SupportApiKey) => (
        <Space size={6}>
          <KeyOutlined />
          <span>{value}</span>
          {record.is_active ? <Tag color="green">启用</Tag> : null}
        </Space>
      ),
    },
    {
      title: 'Key',
      dataIndex: 'masked_api_key',
      key: 'masked_api_key',
    },
    {
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
      render: () => <Tag>DashScope / 阿里云百炼</Tag>,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: API.SupportApiKey) => (
        <Space size={4}>
          <Tooltip title="测试">
            <Button
              size="small"
              type="text"
              icon={<ExperimentOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTestSaved(record)}
              aria-label={`测试 ${record.name}`}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              size="small"
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
              aria-label={`编辑 ${record.name}`}
            />
          </Tooltip>
          <Tooltip title="设为启用">
            <Button
              size="small"
              type="text"
              icon={<CheckCircleOutlined />}
              disabled={record.is_active}
              onClick={() => handleActivate(record)}
              aria-label={`启用 ${record.name}`}
            />
          </Tooltip>
          <Popconfirm title="删除这个 API Key？" onConfirm={() => handleDelete(record)}>
            <Tooltip title="删除">
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                aria-label={`删除 ${record.name}`}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="supportops-section">
      <div className="supportops-section__header">
        <div>
          <div className="supportops-section__title">API Key 管理</div>
          <div className="supportops-section__meta">当前仅支持 DashScope / 阿里云百炼，Agent 优先使用启用项</div>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          新增
        </Button>
      </div>

      <Table
        className="supportops-api-key-table"
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={keys}
        pagination={false}
        scroll={{ x: 560 }}
      />

      <Modal
        title={editing ? '编辑 API Key' : '新增 API Key'}
        open={modalOpen}
        confirmLoading={submitting}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="supportops-api-key-form">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="DashScope" />
          </Form.Item>
          <Form.Item name="provider" hidden initialValue="dashscope">
            <Input />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={editing ? [] : [{ required: true, message: '请输入 API Key' }]}
            extra={editing ? '留空则不修改现有 API Key；点击测试会验证已保存的 key' : '请填写阿里云百炼 Model Studio 的 DashScope API Key'}
          >
            <Input.Password placeholder={editing ? '留空则不修改' : 'sk-xxxxxxxx'} autoComplete="off" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model" label="对话模型" rules={[{ required: true, message: '请输入模型名' }]}>
            <Input placeholder="qwen-plus" />
          </Form.Item>
          <Form.Item
            name="embedding_model"
            label="Embedding 模型"
            rules={[{ required: true, message: '请输入 Embedding 模型名' }]}
          >
            <Input placeholder="text-embedding-v3" />
          </Form.Item>
          <Form.Item>
            <Button icon={<ExperimentOutlined />} loading={testingCurrent} onClick={handleTestCurrentConfig}>
              测试当前配置
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
