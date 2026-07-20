import * as api from '@/api'
import { userActions, userState } from '@/store/user'
import {
  ApartmentOutlined,
  ArrowRightOutlined,
  CheckCircleFilled,
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Button, Form, Input, Tabs, TabsProps } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSnapshot } from 'valtio'
import styles from './index.module.scss'

export default function Login() {
  const user = useSnapshot(userState)
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login')
  const [form] = Form.useForm<{
    username: string
    password: string
    repeatPassword: string
  }>()

  useEffect(() => {
    if (user.username) {
      form.setFieldValue('username', user.username)
    }
  }, [form, user.username])

  async function login() {
    const { username, password } = form.getFieldsValue()
    const { data } = await api.user.login({ username, password })
    window.$app.message.success('登录成功')
    userActions.setUsername(username)
    userActions.setToken(data.access_token)
    navigate('/')
  }

  async function register() {
    const { username, password } = form.getFieldsValue()
    await api.user.register({ username, password })
    window.$app.message.success('注册成功，请登录')
    form.setFieldValue('password', '')
    form.setFieldValue('repeatPassword', '')
    setActiveTab('login')
  }

  const usernameField = (
    <Form.Item
      label="邮箱或用户名"
      name="username"
      rules={[{ required: true, message: '请输入邮箱或用户名' }]}
    >
      <Input
        prefix={<UserOutlined aria-hidden />}
        placeholder="请输入邮箱或用户名"
        size="large"
        autoComplete="username"
      />
    </Form.Item>
  )

  const passwordField = (
    <Form.Item
      label="密码"
      name="password"
      rules={[{ required: true, message: '请输入密码' }]}
    >
      <Input.Password
        prefix={<LockOutlined aria-hidden />}
        placeholder="请输入密码"
        size="large"
        autoComplete={activeTab === 'login' ? 'current-password' : 'new-password'}
        onChange={() => form.setFieldValue('repeatPassword', '')}
      />
    </Form.Item>
  )

  const tabs: TabsProps['items'] = [
    {
      key: 'login',
      label: '登录',
      children: (
        <Form form={form} onFinish={login} layout="vertical" requiredMark={false}>
          {usernameField}
          {passwordField}
          <Button
            className={styles['login-button']}
            type="primary"
            htmlType="submit"
            size="large"
          >
            进入工作台 <ArrowRightOutlined />
          </Button>
        </Form>
      ),
    },
    {
      key: 'register',
      label: '创建账户',
      children: (
        <Form form={form} onFinish={register} layout="vertical" requiredMark={false}>
          {usernameField}
          {passwordField}
          <Form.Item
            label="确认密码"
            name="repeatPassword"
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (value !== getFieldValue('password')) {
                    return Promise.reject(new Error('两次密码不一致'))
                  }
                  return Promise.resolve()
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined aria-hidden />}
              placeholder="请再次输入密码"
              size="large"
              autoComplete="new-password"
            />
          </Form.Item>
          <Button
            className={styles['login-button']}
            type="primary"
            htmlType="submit"
            size="large"
          >
            创建并继续 <ArrowRightOutlined />
          </Button>
        </Form>
      ),
    },
  ]

  return (
    <main className={styles['login-page']}>
      <section className={styles['login-shell']} aria-label="SupportOps 账户入口">
        <aside className={styles['login-story']}>
          <div className={styles['brand']}>
            <span className={styles['brand-mark']}><ApartmentOutlined /></span>
            <span>
              <strong>SupportOps</strong>
              <small>AI SERVICE OPERATIONS</small>
            </span>
          </div>

          <div className={styles['story-copy']}>
            <p className={styles['eyebrow']}>CUSTOMER SUPPORT CONTROL CENTER</p>
            <h1>让每一次客户请求，<br />都有证据与处理路径。</h1>
            <p className={styles['story-description']}>
              统一完成意图识别、知识检索、风险升级与人工审核，让客服决策更快，也更可追溯。
            </p>
          </div>

          <div className={styles['workflow']} aria-label="Agent 工作流能力">
            <div><span>01</span><strong>识别问题与风险</strong><CheckCircleFilled /></div>
            <div><span>02</span><strong>检索知识与工单</strong><CheckCircleFilled /></div>
            <div><span>03</span><strong>生成并审核回复</strong><CheckCircleFilled /></div>
          </div>

          <div className={styles['story-foot']}>
            <SafetyCertificateOutlined /> 人工审核与执行轨迹全程留痕
          </div>
        </aside>

        <section className={styles['login-panel']}>
          <div className={styles['panel-heading']}>
            <span className={styles['mobile-brand']}><ApartmentOutlined /> SupportOps</span>
            <p>{activeTab === 'login' ? '欢迎回来' : '开始使用 SupportOps'}</p>
            <h2>{activeTab === 'login' ? '登录运营工作台' : '创建运营账户'}</h2>
            <span>{activeTab === 'login' ? '继续处理客户问题与待审核任务。' : '注册后即可配置 Agent 与知识资产。'}</span>
          </div>
          <Tabs
            className={styles['login-tabs']}
            items={tabs}
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as 'login' | 'register')}
            destroyOnHidden
          />
          <p className={styles['security-note']}>
            <LockOutlined /> 凭据仅用于访问你的本地 SupportOps 服务
          </p>
        </section>
      </section>
    </main>
  )
}
